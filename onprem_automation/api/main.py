"""
FastAPI Main Application

Enterprise-grade REST API for the automation platform.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import os
import logging

# Try FastAPI import
try:
    from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None

logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

if FASTAPI_AVAILABLE:
    class HealthResponse(BaseModel):
        status: str
        version: str
        timestamp: str
        components: Dict[str, Any]

    class JobCreate(BaseModel):
        name: str = Field(..., min_length=1, max_length=255)
        description: Optional[str] = None
        module: str = Field(..., min_length=1)
        action: str = Field(..., min_length=1)
        parameters: Dict[str, Any] = Field(default_factory=dict)
        timeout: int = Field(default=3600, ge=1, le=86400)
        retry_count: int = Field(default=0, ge=0, le=10)
        requires_approval: bool = False

    class JobResponse(BaseModel):
        id: str
        name: str
        description: Optional[str]
        module: str
        action: str
        parameters: Dict[str, Any]
        timeout: int
        is_active: bool
        created_at: Optional[str]

        class Config:
            from_attributes = True

    class JobExecuteRequest(BaseModel):
        parameters: Dict[str, Any] = Field(default_factory=dict)
        async_mode: bool = True

    class ExecutionResponse(BaseModel):
        id: str
        job_id: str
        status: str
        parameters: Dict[str, Any]
        result: Optional[Dict[str, Any]]
        error: Optional[str]
        started_at: Optional[str]
        completed_at: Optional[str]
        duration: Optional[float]

    class WorkflowCreate(BaseModel):
        name: str = Field(..., min_length=1, max_length=255)
        description: Optional[str] = None
        definition: Dict[str, Any]
        category: Optional[str] = None
        tags: List[str] = Field(default_factory=list)
        timeout: int = Field(default=7200, ge=1)

    class WorkflowResponse(BaseModel):
        id: str
        name: str
        description: Optional[str]
        version: int
        status: str
        category: Optional[str]
        tags: List[str]
        created_at: Optional[str]

    class ScheduleCreate(BaseModel):
        name: str
        description: Optional[str] = None
        job_id: Optional[str] = None
        workflow_id: Optional[str] = None
        parameters: Dict[str, Any] = Field(default_factory=dict)
        schedule_type: str = "cron"
        cron_expression: Optional[str] = None
        interval_seconds: Optional[int] = None
        timezone: str = "UTC"

    class ModuleInfo(BaseModel):
        name: str
        description: str
        actions: List[str]
        health: str

    class PaginatedResponse(BaseModel):
        items: List[Any]
        total: int
        page: int
        page_size: int
        pages: int


def create_app() -> "FastAPI":
    """Create and configure FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed. Run: pip install fastapi uvicorn")

    app = FastAPI(
        title="OnPrem Automation Platform",
        description="""
## Enterprise On-Premises Infrastructure Automation

A comprehensive platform for automating infrastructure operations:

- **VMware**: VM provisioning, snapshots, power operations
- **Network**: VLAN management, firewall rules, device configuration
- **Patching**: Windows/Linux update management
- **Backup**: Validation and compliance checking
- **Capacity**: Resource monitoring and forecasting
- **Incident**: Automated remediation

### Authentication
Use JWT tokens in the Authorization header:
```
Authorization: Bearer <token>
```

### Rate Limits
- 1000 requests per minute for authenticated users
- 100 requests per minute for unauthenticated

### WebSocket
Real-time updates available at `/ws/events`
        """,
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: "FastAPI"):
    """Register all API routes."""

    # ==================== Health & Info ====================

    @app.get("/", tags=["Info"])
    async def root():
        """API root - redirects to documentation."""
        return {
            "name": "OnPrem Automation Platform",
            "version": "2.0.0",
            "docs": "/api/docs",
            "health": "/health",
        }

    @app.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health_check():
        """Comprehensive health check."""
        from ..database.session import check_db_health

        components = {
            "api": {"status": "healthy"},
            "database": check_db_health(),
        }

        # Check automation engine
        try:
            from ..core.engine import AutomationEngine
            from ..core.config import Config
            engine = AutomationEngine(Config())
            engine_health = engine.health_check()
            components["automation_engine"] = {
                "status": "healthy",
                "modules": len(engine_health)
            }
        except Exception as e:
            components["automation_engine"] = {"status": "unhealthy", "error": str(e)}

        overall_status = "healthy" if all(
            c.get("status") == "healthy" for c in components.values()
        ) else "degraded"

        return HealthResponse(
            status=overall_status,
            version="2.0.0",
            timestamp=datetime.utcnow().isoformat(),
            components=components
        )

    @app.get("/api/v1/modules", response_model=List[ModuleInfo], tags=["Modules"])
    async def list_modules():
        """List all available automation modules."""
        from ..core.engine import AutomationEngine
        from ..core.config import Config

        engine = AutomationEngine(Config())
        modules = []

        for name, module in engine.modules.items():
            health = module.health_check()
            modules.append(ModuleInfo(
                name=name,
                description=getattr(module, 'description', f'{name} automation module'),
                actions=list(getattr(module, 'actions', {}).keys()),
                health=health.get("status", "unknown")
            ))

        return modules

    # ==================== Jobs ====================

    @app.get("/api/v1/jobs", tags=["Jobs"])
    async def list_jobs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        module: Optional[str] = None,
        is_active: Optional[bool] = None,
    ):
        """List all jobs with pagination."""
        from ..database.session import DatabaseSession
        from ..database.models import Job

        with DatabaseSession() as session:
            query = session.query(Job)

            if module:
                query = query.filter(Job.module == module)
            if is_active is not None:
                query = query.filter(Job.is_active == is_active)

            total = query.count()
            jobs = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "items": [j.to_dict() for j in jobs],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size
            }

    @app.post("/api/v1/jobs", response_model=JobResponse, status_code=201, tags=["Jobs"])
    async def create_job(job: JobCreate):
        """Create a new job definition."""
        from ..database.session import DatabaseSession
        from ..database.models import Job

        with DatabaseSession() as session:
            db_job = Job(
                name=job.name,
                description=job.description,
                module=job.module,
                action=job.action,
                parameters=job.parameters,
                timeout=job.timeout,
                retry_count=job.retry_count,
                requires_approval=job.requires_approval,
            )
            session.add(db_job)
            session.flush()
            return db_job.to_dict()

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
    async def get_job(job_id: str):
        """Get job by ID."""
        from ..database.session import DatabaseSession
        from ..database.models import Job

        with DatabaseSession() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return job.to_dict()

    @app.post("/api/v1/jobs/{job_id}/execute", tags=["Jobs"])
    async def execute_job(
        job_id: str,
        request: JobExecuteRequest,
        background_tasks: BackgroundTasks
    ):
        """Execute a job."""
        from ..database.session import DatabaseSession
        from ..database.models import Job, JobExecution, JobStatus
        import uuid

        with DatabaseSession() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            # Create execution record
            execution = JobExecution(
                id=str(uuid.uuid4()),
                job_id=job_id,
                status=JobStatus.PENDING.value,
                parameters={**job.parameters, **request.parameters},
                trigger_type="api",
            )
            session.add(execution)
            session.flush()
            execution_id = execution.id
            execution_dict = execution.to_dict()

        # Execute in background if async
        if request.async_mode:
            background_tasks.add_task(_run_job_execution, execution_id)
            return {"execution_id": execution_id, "status": "pending", **execution_dict}
        else:
            result = await _run_job_execution(execution_id)
            return result

    @app.get("/api/v1/jobs/{job_id}/executions", tags=["Jobs"])
    async def list_job_executions(
        job_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        status: Optional[str] = None,
    ):
        """List executions for a job."""
        from ..database.session import DatabaseSession
        from ..database.models import JobExecution

        with DatabaseSession() as session:
            query = session.query(JobExecution).filter(JobExecution.job_id == job_id)

            if status:
                query = query.filter(JobExecution.status == status)

            query = query.order_by(JobExecution.started_at.desc())
            total = query.count()
            executions = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "items": [e.to_dict() for e in executions],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    # ==================== Executions ====================

    @app.get("/api/v1/executions/{execution_id}", response_model=ExecutionResponse, tags=["Executions"])
    async def get_execution(execution_id: str):
        """Get execution details."""
        from ..database.session import DatabaseSession
        from ..database.models import JobExecution

        with DatabaseSession() as session:
            execution = session.query(JobExecution).filter(
                JobExecution.id == execution_id
            ).first()
            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")
            return execution.to_dict()

    @app.post("/api/v1/executions/{execution_id}/cancel", tags=["Executions"])
    async def cancel_execution(execution_id: str):
        """Cancel a running execution."""
        from ..database.session import DatabaseSession
        from ..database.models import JobExecution, JobStatus

        with DatabaseSession() as session:
            execution = session.query(JobExecution).filter(
                JobExecution.id == execution_id
            ).first()
            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")

            if execution.status not in [JobStatus.PENDING.value, JobStatus.RUNNING.value]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel execution in {execution.status} state"
                )

            execution.status = JobStatus.CANCELLED.value
            execution.completed_at = datetime.utcnow()
            return {"status": "cancelled", "execution_id": execution_id}

    # ==================== Workflows ====================

    @app.get("/api/v1/workflows", tags=["Workflows"])
    async def list_workflows(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        category: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """List all workflows."""
        from ..database.session import DatabaseSession
        from ..database.models import Workflow

        with DatabaseSession() as session:
            query = session.query(Workflow)

            if category:
                query = query.filter(Workflow.category == category)
            if status:
                query = query.filter(Workflow.status == status)

            total = query.count()
            workflows = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "items": [w.to_dict() for w in workflows],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @app.post("/api/v1/workflows", response_model=WorkflowResponse, status_code=201, tags=["Workflows"])
    async def create_workflow(workflow: WorkflowCreate):
        """Create a new workflow."""
        from ..database.session import DatabaseSession
        from ..database.models import Workflow

        with DatabaseSession() as session:
            db_workflow = Workflow(
                name=workflow.name,
                description=workflow.description,
                definition=workflow.definition,
                category=workflow.category,
                tags=workflow.tags,
                timeout=workflow.timeout,
            )
            session.add(db_workflow)
            session.flush()
            return db_workflow.to_dict()

    @app.post("/api/v1/workflows/{workflow_id}/execute", tags=["Workflows"])
    async def execute_workflow(
        workflow_id: str,
        request: JobExecuteRequest,
        background_tasks: BackgroundTasks
    ):
        """Execute a workflow."""
        from ..database.session import DatabaseSession
        from ..database.models import Workflow, WorkflowExecution, JobStatus
        import uuid

        with DatabaseSession() as session:
            workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")

            execution = WorkflowExecution(
                id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                status=JobStatus.PENDING.value,
                parameters=request.parameters,
                trigger_type="api",
            )
            session.add(execution)
            session.flush()
            execution_id = execution.id

        if request.async_mode:
            background_tasks.add_task(_run_workflow_execution, execution_id)
            return {"execution_id": execution_id, "status": "pending"}
        else:
            result = await _run_workflow_execution(execution_id)
            return result

    # ==================== Schedules ====================

    @app.get("/api/v1/schedules", tags=["Schedules"])
    async def list_schedules(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        is_active: Optional[bool] = None,
    ):
        """List all schedules."""
        from ..database.session import DatabaseSession
        from ..database.models import Schedule

        with DatabaseSession() as session:
            query = session.query(Schedule)

            if is_active is not None:
                query = query.filter(Schedule.is_active == is_active)

            total = query.count()
            schedules = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "items": [s.to_dict() for s in schedules],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @app.post("/api/v1/schedules", status_code=201, tags=["Schedules"])
    async def create_schedule(schedule: ScheduleCreate):
        """Create a new schedule."""
        from ..database.session import DatabaseSession
        from ..database.models import Schedule

        if not schedule.job_id and not schedule.workflow_id:
            raise HTTPException(
                status_code=400,
                detail="Either job_id or workflow_id is required"
            )

        with DatabaseSession() as session:
            db_schedule = Schedule(
                name=schedule.name,
                description=schedule.description,
                job_id=schedule.job_id,
                workflow_id=schedule.workflow_id,
                parameters=schedule.parameters,
                schedule_type=schedule.schedule_type,
                cron_expression=schedule.cron_expression,
                interval_seconds=schedule.interval_seconds,
                timezone=schedule.timezone,
            )
            session.add(db_schedule)
            session.flush()
            return db_schedule.to_dict()

    # ==================== Direct Execution ====================

    @app.post("/api/v1/execute/{module}/{action}", tags=["Execute"])
    async def execute_direct(
        module: str,
        action: str,
        parameters: Dict[str, Any] = {},
        background_tasks: BackgroundTasks = None,
        async_mode: bool = True,
    ):
        """Execute a module action directly."""
        from ..core.engine import AutomationEngine
        from ..core.config import Config

        engine = AutomationEngine(Config())

        if module not in engine.modules:
            raise HTTPException(status_code=404, detail=f"Module '{module}' not found")

        if async_mode and background_tasks:
            background_tasks.add_task(engine.run_action, module, action, **parameters)
            return {"status": "pending", "module": module, "action": action}

        result = await engine.run_action(module, action, **parameters)
        return result

    # ==================== Audit Logs ====================

    @app.get("/api/v1/audit-logs", tags=["Audit"])
    async def list_audit_logs(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """List audit logs with filtering."""
        from ..database.session import DatabaseSession
        from ..database.models import AuditLog

        with DatabaseSession() as session:
            query = session.query(AuditLog)

            if resource_type:
                query = query.filter(AuditLog.resource_type == resource_type)
            if action:
                query = query.filter(AuditLog.action == action)
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            if start_date:
                query = query.filter(AuditLog.timestamp >= start_date)
            if end_date:
                query = query.filter(AuditLog.timestamp <= end_date)

            query = query.order_by(AuditLog.timestamp.desc())
            total = query.count()
            logs = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "items": [log.to_dict() for log in logs],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    # ==================== WebSocket ====================

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """WebSocket endpoint for real-time events."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                # Echo back for now - will integrate with event bus
                await websocket.send_json({
                    "type": "ack",
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat()
                })
        except Exception:
            pass


async def _run_job_execution(execution_id: str) -> dict:
    """Run a job execution."""
    from ..database.session import DatabaseSession
    from ..database.models import JobExecution, Job, JobStatus
    from ..core.engine import AutomationEngine
    from ..core.config import Config

    with DatabaseSession() as session:
        execution = session.query(JobExecution).filter(
            JobExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": "Execution not found"}

        job = session.query(Job).filter(Job.id == execution.job_id).first()
        if not job:
            return {"error": "Job not found"}

        # Update status
        execution.status = JobStatus.RUNNING.value
        execution.started_at = datetime.utcnow()
        session.commit()

        # Run the job
        try:
            engine = AutomationEngine(Config())
            result = await engine.run_action(
                job.module,
                job.action,
                **execution.parameters
            )

            execution.status = JobStatus.SUCCESS.value if result.get("status") == "success" else JobStatus.FAILED.value
            execution.result = result
            execution.completed_at = datetime.utcnow()
            execution.duration = (execution.completed_at - execution.started_at).total_seconds()

        except Exception as e:
            execution.status = JobStatus.FAILED.value
            execution.error = str(e)
            execution.completed_at = datetime.utcnow()
            execution.duration = (execution.completed_at - execution.started_at).total_seconds()

        return execution.to_dict()


async def _run_workflow_execution(execution_id: str) -> dict:
    """Run a workflow execution."""
    from ..database.session import DatabaseSession
    from ..database.models import WorkflowExecution, Workflow, JobStatus

    with DatabaseSession() as session:
        execution = session.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": "Execution not found"}

        workflow = session.query(Workflow).filter(
            Workflow.id == execution.workflow_id
        ).first()
        if not workflow:
            return {"error": "Workflow not found"}

        execution.status = JobStatus.RUNNING.value
        execution.started_at = datetime.utcnow()
        session.commit()

        try:
            from ..workflows.engine import WorkflowEngine
            wf_engine = WorkflowEngine()
            result = await wf_engine.execute(
                workflow.definition,
                execution.parameters,
                execution_id=execution_id
            )

            execution.status = JobStatus.SUCCESS.value if result.get("status") == "success" else JobStatus.FAILED.value
            execution.result = result
            execution.completed_at = datetime.utcnow()
            execution.duration = (execution.completed_at - execution.started_at).total_seconds()
            execution.completed_steps = result.get("completed_steps", [])

        except Exception as e:
            execution.status = JobStatus.FAILED.value
            execution.error = str(e)
            execution.completed_at = datetime.utcnow()

        return execution.to_dict()


# Create default app instance
app = None
if FASTAPI_AVAILABLE:
    app = create_app()

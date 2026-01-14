"""
Workflow Execution Engine

Executes workflows with:
- Parallel step execution
- Conditional logic
- Error handling and retry
- Template rendering
- State management
"""

from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import re
import logging
import traceback

from .dsl import (
    WorkflowDefinition, WorkflowDSL, Step, StepType,
    OnErrorAction, Condition
)

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class StepResult:
    """Result of a step execution."""
    name: str
    status: ExecutionStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration: float = 0.0
    attempts: int = 1


@dataclass
class WorkflowContext:
    """
    Workflow execution context.

    Provides access to:
    - inputs: Input parameters
    - steps: Results from completed steps
    - env: Environment variables
    - secrets: Secret values (resolved)
    """
    inputs: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, StepResult] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = None) -> Any:
        """Get value by dot-notation path."""
        parts = path.split(".")
        obj = self

        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            elif isinstance(obj, dict) and part in obj:
                obj = obj[part]
            elif isinstance(obj, StepResult) and part in ["result", "status", "error"]:
                obj = getattr(obj, part)
            else:
                return default

        return obj

    def set(self, path: str, value: Any):
        """Set value by dot-notation path."""
        parts = path.split(".")
        if len(parts) == 1:
            self.variables[path] = value
        else:
            target = self.variables
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value


class TemplateEngine:
    """
    Template engine for parameter rendering.

    Supports Jinja2-style expressions:
    - {{ inputs.vm_name }}
    - {{ steps.provision.result.vm_id }}
    - {{ env.DATACENTER }}
    """

    # Pattern for template expressions
    TEMPLATE_PATTERN = re.compile(r'\{\{\s*(.+?)\s*\}\}')

    @classmethod
    def render(cls, template: Any, context: WorkflowContext) -> Any:
        """Render a template value against context."""
        if isinstance(template, str):
            return cls._render_string(template, context)
        elif isinstance(template, dict):
            return {k: cls.render(v, context) for k, v in template.items()}
        elif isinstance(template, list):
            return [cls.render(item, context) for item in template]
        return template

    @classmethod
    def _render_string(cls, template: str, context: WorkflowContext) -> str:
        """Render string template."""
        def replace_match(match):
            expression = match.group(1).strip()
            return str(cls._evaluate_expression(expression, context))

        result = cls.TEMPLATE_PATTERN.sub(replace_match, template)

        # Try to convert to appropriate type
        if result.lower() == "true":
            return True
        elif result.lower() == "false":
            return False
        try:
            return int(result)
        except ValueError:
            try:
                return float(result)
            except ValueError:
                return result

    @classmethod
    def _evaluate_expression(cls, expression: str, context: WorkflowContext) -> Any:
        """Evaluate a template expression."""
        # Handle comparison operators
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in expression:
                left, right = expression.split(op, 1)
                left_val = cls._evaluate_expression(left.strip(), context)
                right_val = cls._evaluate_expression(right.strip(), context)

                # Remove quotes from string literals
                if isinstance(right_val, str) and right_val.startswith("'") and right_val.endswith("'"):
                    right_val = right_val[1:-1]

                if op == "==":
                    return str(left_val) == str(right_val)
                elif op == "!=":
                    return str(left_val) != str(right_val)
                elif op == ">=":
                    return float(left_val) >= float(right_val)
                elif op == "<=":
                    return float(left_val) <= float(right_val)
                elif op == ">":
                    return float(left_val) > float(right_val)
                elif op == "<":
                    return float(left_val) < float(right_val)

        # Simple dot-notation path
        return context.get(expression)


class StepExecutor:
    """Executes individual workflow steps."""

    def __init__(self, engine: "WorkflowEngine"):
        self.engine = engine

    async def execute(
        self,
        step: Step,
        context: WorkflowContext,
    ) -> StepResult:
        """Execute a single step."""
        result = StepResult(
            name=step.name,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        try:
            if step.step_type == StepType.ACTION:
                result = await self._execute_action(step, context, result)
            elif step.step_type == StepType.PARALLEL:
                result = await self._execute_parallel(step, context, result)
            elif step.step_type == StepType.LOOP:
                result = await self._execute_loop(step, context, result)
            elif step.step_type == StepType.WAIT:
                result = await self._execute_wait(step, context, result)
            elif step.step_type == StepType.SCRIPT:
                result = await self._execute_script(step, context, result)
            elif step.step_type == StepType.APPROVAL:
                result = await self._execute_approval(step, context, result)

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error = str(e)
            logger.error(f"Step {step.name} failed: {e}\n{traceback.format_exc()}")

        result.completed_at = datetime.utcnow()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result

    async def _execute_action(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute an action step."""
        from ..core.engine import AutomationEngine
        from ..core.config import Config

        # Render parameters
        params = TemplateEngine.render(step.parameters, context)

        # Get automation engine
        engine = AutomationEngine(Config())

        # Execute with retry
        attempts = 0
        max_attempts = step.retry.max_attempts if step.retry else 1
        delay = step.retry.delay_seconds if step.retry else 0

        while attempts < max_attempts:
            attempts += 1
            try:
                action_result = await engine.run_action(
                    step.module,
                    step.action,
                    **params
                )

                if action_result.get("status") == "success":
                    result.status = ExecutionStatus.SUCCESS
                    result.result = action_result
                    break
                else:
                    if attempts < max_attempts:
                        await asyncio.sleep(delay)
                        delay *= step.retry.backoff_multiplier if step.retry else 1
                    else:
                        result.status = ExecutionStatus.FAILED
                        result.error = action_result.get("error", "Action failed")
                        result.result = action_result

            except Exception as e:
                if attempts < max_attempts:
                    await asyncio.sleep(delay)
                    delay *= step.retry.backoff_multiplier if step.retry else 1
                else:
                    raise

        result.attempts = attempts
        return result

    async def _execute_parallel(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute parallel steps."""
        tasks = []
        for parallel_step in step.parallel_steps:
            task = asyncio.create_task(self.execute(parallel_step, context))
            tasks.append(task)

        parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_success = True
        step_results = {}
        for i, res in enumerate(parallel_results):
            if isinstance(res, Exception):
                all_success = False
                step_results[step.parallel_steps[i].name] = {
                    "status": "failed",
                    "error": str(res)
                }
            else:
                step_results[step.parallel_steps[i].name] = res.result
                if res.status != ExecutionStatus.SUCCESS:
                    all_success = False

        result.status = ExecutionStatus.SUCCESS if all_success else ExecutionStatus.FAILED
        result.result = step_results
        return result

    async def _execute_loop(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute loop step."""
        # Evaluate loop items
        items = TemplateEngine.render(step.loop_items, context)
        if isinstance(items, str):
            items = context.get(items, [])

        loop_results = []
        for item in items:
            # Create loop context
            loop_context = WorkflowContext(
                inputs=context.inputs,
                steps=context.steps,
                env=context.env,
                secrets=context.secrets,
                variables={**context.variables, step.loop_variable: item}
            )

            # Execute action
            loop_step = Step(
                name=f"{step.name}_{len(loop_results)}",
                step_type=StepType.ACTION,
                module=step.module,
                action=step.action,
                parameters=step.parameters,
            )
            loop_result = await self._execute_action(loop_step, loop_context, StepResult(
                name=loop_step.name,
                status=ExecutionStatus.RUNNING,
                started_at=datetime.utcnow(),
            ))
            loop_results.append(loop_result.result)

        result.status = ExecutionStatus.SUCCESS
        result.result = {"items": loop_results}
        return result

    async def _execute_wait(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute wait step."""
        if step.wait_seconds > 0:
            await asyncio.sleep(step.wait_seconds)
            result.status = ExecutionStatus.SUCCESS
            result.result = {"waited_seconds": step.wait_seconds}
        elif step.wait_until:
            # Poll until condition is true
            timeout = step.timeout
            interval = 10
            elapsed = 0

            while elapsed < timeout:
                condition_met = TemplateEngine.render(step.wait_until, context)
                if condition_met:
                    result.status = ExecutionStatus.SUCCESS
                    result.result = {"waited_seconds": elapsed}
                    return result

                await asyncio.sleep(interval)
                elapsed += interval

            result.status = ExecutionStatus.FAILED
            result.error = f"Wait condition not met within {timeout}s"

        return result

    async def _execute_script(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute script step."""
        import subprocess

        script = TemplateEngine.render(step.script, context)

        if step.script_type == "bash":
            proc = await asyncio.create_subprocess_shell(
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                result.status = ExecutionStatus.SUCCESS
                result.result = {
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode(),
                    "return_code": proc.returncode,
                }
            else:
                result.status = ExecutionStatus.FAILED
                result.error = stderr.decode()
                result.result = {"return_code": proc.returncode}

        elif step.script_type == "python":
            # Execute Python script in subprocess
            proc = await asyncio.create_subprocess_exec(
                "python", "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                result.status = ExecutionStatus.SUCCESS
                result.result = {
                    "stdout": stdout.decode(),
                    "return_code": proc.returncode,
                }
            else:
                result.status = ExecutionStatus.FAILED
                result.error = stderr.decode()

        return result

    async def _execute_approval(
        self,
        step: Step,
        context: WorkflowContext,
        result: StepResult,
    ) -> StepResult:
        """Execute approval step (stub - needs external integration)."""
        # In a real implementation, this would:
        # 1. Create an approval request in the database
        # 2. Send notifications to approvers
        # 3. Wait for approval/rejection
        # 4. Timeout if not approved in time

        logger.info(f"Approval required from: {step.approvers}")

        # For now, auto-approve (replace with real approval flow)
        result.status = ExecutionStatus.SUCCESS
        result.result = {"auto_approved": True, "approvers": step.approvers}

        return result


class WorkflowEngine:
    """
    Main workflow execution engine.

    Orchestrates workflow execution with:
    - Step dependency resolution
    - Parallel execution
    - Error handling
    - State management
    """

    def __init__(self, max_parallel: int = 5):
        self.max_parallel = max_parallel
        self.step_executor = StepExecutor(self)
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def execute(
        self,
        workflow_def: Dict[str, Any],
        inputs: Dict[str, Any] = None,
        execution_id: str = None,
    ) -> Dict[str, Any]:
        """
        Execute a workflow.

        Args:
            workflow_def: Workflow definition (dict or YAML string)
            inputs: Input parameters
            execution_id: Optional execution ID for tracking

        Returns:
            Execution result
        """
        # Parse workflow
        if isinstance(workflow_def, str):
            workflow = WorkflowDSL.parse(workflow_def)
        else:
            workflow = WorkflowDSL.from_dict(workflow_def)

        # Validate
        errors = WorkflowDSL.validate(workflow)
        if errors:
            return {
                "status": "failed",
                "error": f"Validation errors: {', '.join(errors)}",
            }

        # Create context
        context = WorkflowContext(
            inputs=self._resolve_inputs(workflow, inputs or {}),
            env=dict(__import__("os").environ),
        )

        # Execute steps
        result = await self._execute_workflow(workflow, context)

        # Resolve outputs
        outputs = {}
        for name, output_def in workflow.outputs.items():
            outputs[name] = TemplateEngine.render(output_def.value, context)

        return {
            "status": result["status"],
            "outputs": outputs,
            "completed_steps": result["completed_steps"],
            "failed_steps": result.get("failed_steps", []),
            "error": result.get("error"),
        }

    def _resolve_inputs(
        self,
        workflow: WorkflowDefinition,
        provided: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve and validate workflow inputs."""
        resolved = {}

        for name, input_def in workflow.inputs.items():
            if name in provided:
                resolved[name] = provided[name]
            elif input_def.default is not None:
                resolved[name] = input_def.default
            elif input_def.required:
                raise ValueError(f"Required input '{name}' not provided")

        return resolved

    async def _execute_workflow(
        self,
        workflow: WorkflowDefinition,
        context: WorkflowContext,
    ) -> Dict[str, Any]:
        """Execute all workflow steps."""
        completed_steps = []
        failed_steps = []
        pending_steps = list(workflow.steps)

        while pending_steps:
            # Find steps that are ready to run
            ready_steps = self._get_ready_steps(pending_steps, context)

            if not ready_steps:
                if pending_steps:
                    # Deadlock - remaining steps have unmet dependencies
                    return {
                        "status": "failed",
                        "error": f"Workflow deadlock: {[s.name for s in pending_steps]}",
                        "completed_steps": completed_steps,
                        "failed_steps": failed_steps,
                    }
                break

            # Execute ready steps (potentially in parallel)
            tasks = []
            for step in ready_steps:
                task = self._execute_step_with_semaphore(step, context)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for step, result in zip(ready_steps, results):
                pending_steps.remove(step)

                if isinstance(result, Exception):
                    failed_steps.append(step.name)
                    context.steps[step.name] = StepResult(
                        name=step.name,
                        status=ExecutionStatus.FAILED,
                        error=str(result),
                    )

                    if step.on_error == OnErrorAction.FAIL:
                        return {
                            "status": "failed",
                            "error": f"Step '{step.name}' failed: {result}",
                            "completed_steps": completed_steps,
                            "failed_steps": failed_steps,
                        }

                else:
                    context.steps[step.name] = result

                    if result.status == ExecutionStatus.SUCCESS:
                        completed_steps.append(step.name)
                    else:
                        failed_steps.append(step.name)

                        if step.on_error == OnErrorAction.FAIL:
                            return {
                                "status": "failed",
                                "error": f"Step '{step.name}' failed: {result.error}",
                                "completed_steps": completed_steps,
                                "failed_steps": failed_steps,
                            }

        return {
            "status": "success" if not failed_steps else "partial",
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
        }

    async def _execute_step_with_semaphore(
        self,
        step: Step,
        context: WorkflowContext,
    ) -> StepResult:
        """Execute step with concurrency control."""
        async with self._semaphore:
            # Check condition
            if step.condition:
                condition_met = TemplateEngine.render(step.condition, context)
                if not condition_met:
                    return StepResult(
                        name=step.name,
                        status=ExecutionStatus.SUCCESS,
                        result={"skipped": True, "reason": "condition not met"},
                    )

            return await self.step_executor.execute(step, context)

    def _get_ready_steps(
        self,
        pending: List[Step],
        context: WorkflowContext,
    ) -> List[Step]:
        """Get steps that are ready to execute (dependencies met)."""
        ready = []
        completed_names = set(context.steps.keys())

        for step in pending:
            if all(dep in completed_names for dep in step.depends_on):
                ready.append(step)

        return ready

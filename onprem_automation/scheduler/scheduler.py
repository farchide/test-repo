"""
Job Scheduler

Central scheduler for managing and executing scheduled jobs.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import heapq

from .job import ScheduledJob, JobStatus, JobTrigger, CronTrigger


class JobExecutor:
    """Executes scheduled jobs."""

    def __init__(self):
        self._logger = logging.getLogger("scheduler.executor")
        self._action_handlers: Dict[str, Callable] = {}
        self._running_jobs: Dict[str, asyncio.Task] = {}

    def register_handler(self, module: str, action: str, handler: Callable) -> None:
        """Register a handler for a module/action combination."""
        key = f"{module}.{action}"
        self._action_handlers[key] = handler
        self._logger.debug(f"Registered handler: {key}")

    async def execute(self, job: ScheduledJob) -> Dict[str, Any]:
        """Execute a job."""
        key = f"{job.module}.{job.action}"
        handler = self._action_handlers.get(key)

        if not handler:
            return {
                "status": "error",
                "error": f"No handler registered for {key}"
            }

        # Track running job
        self._running_jobs[job.id] = asyncio.current_task()

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._run_handler(handler, job),
                timeout=job.timeout
            )
            return result

        except asyncio.TimeoutError:
            return {
                "status": "error",
                "error": f"Job timed out after {job.timeout} seconds"
            }
        except Exception as e:
            self._logger.error(f"Job {job.name} failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
        finally:
            if job.id in self._running_jobs:
                del self._running_jobs[job.id]

    async def _run_handler(self, handler: Callable, job: ScheduledJob) -> Dict[str, Any]:
        """Run the actual handler."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(**job.params)
        else:
            return handler(**job.params)

    def is_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        return job_id in self._running_jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        if job_id in self._running_jobs:
            self._running_jobs[job_id].cancel()
            return True
        return False


class JobStore:
    """Persists scheduled jobs."""

    def __init__(self, storage_path: Optional[str] = None):
        self._storage_path = Path(storage_path) if storage_path else None
        self._jobs: Dict[str, ScheduledJob] = {}
        self._logger = logging.getLogger("scheduler.store")

    def add(self, job: ScheduledJob) -> None:
        """Add a job to the store."""
        self._jobs[job.id] = job
        self._save()

    def update(self, job: ScheduledJob) -> None:
        """Update a job in the store."""
        if job.id in self._jobs:
            self._jobs[job.id] = job
            self._save()

    def remove(self, job_id: str) -> Optional[ScheduledJob]:
        """Remove a job from the store."""
        if job_id in self._jobs:
            job = self._jobs.pop(job_id)
            self._save()
            return job
        return None

    def get(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_by_name(self, name: str) -> Optional[ScheduledJob]:
        """Get a job by name."""
        for job in self._jobs.values():
            if job.name == name:
                return job
        return None

    def get_all(self) -> List[ScheduledJob]:
        """Get all jobs."""
        return list(self._jobs.values())

    def get_enabled(self) -> List[ScheduledJob]:
        """Get all enabled jobs."""
        return [j for j in self._jobs.values() if j.enabled]

    def get_pending(self) -> List[ScheduledJob]:
        """Get jobs with pending next run times."""
        now = datetime.utcnow()
        return [
            j for j in self._jobs.values()
            if j.enabled and j.next_run_time and j.next_run_time <= now
        ]

    def load(self) -> None:
        """Load jobs from storage."""
        if not self._storage_path:
            return

        jobs_file = self._storage_path / "scheduled_jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, 'r') as f:
                    data = json.load(f)
                for job_data in data:
                    job = ScheduledJob.from_dict(job_data)
                    self._jobs[job.id] = job
                self._logger.info(f"Loaded {len(self._jobs)} jobs")
            except Exception as e:
                self._logger.error(f"Failed to load jobs: {e}")

    def _save(self) -> None:
        """Save jobs to storage."""
        if not self._storage_path:
            return

        self._storage_path.mkdir(parents=True, exist_ok=True)
        jobs_file = self._storage_path / "scheduled_jobs.json"

        try:
            data = [job.to_dict() for job in self._jobs.values()]
            with open(jobs_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self._logger.error(f"Failed to save jobs: {e}")


class Scheduler:
    """
    Central job scheduler.

    Example usage:
    ```python
    scheduler = Scheduler()

    # Register action handlers
    scheduler.register_handler("backup", "run_backup", backup_handler)
    scheduler.register_handler("patching", "apply_patches", patch_handler)

    # Add scheduled jobs
    scheduler.add_job(ScheduledJob(
        name="nightly-backup",
        trigger=CronTrigger("0 2 * * *"),
        action="run_backup",
        module="backup",
        params={"target": "all"}
    ))

    # Start scheduler
    await scheduler.start()

    # ... later
    await scheduler.stop()
    ```
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        check_interval: int = 60,  # seconds
        max_concurrent_jobs: int = 10
    ):
        self._store = JobStore(storage_path)
        self._executor = JobExecutor()
        self._check_interval = check_interval
        self._max_concurrent_jobs = max_concurrent_jobs
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._logger = logging.getLogger("scheduler")

        # Event hooks
        self._hooks: Dict[str, List[Callable]] = {
            "job_started": [],
            "job_completed": [],
            "job_failed": [],
        }

    def register_handler(self, module: str, action: str, handler: Callable) -> None:
        """Register a handler for a module/action combination."""
        self._executor.register_handler(module, action, handler)

    def add_job(self, job: ScheduledJob) -> str:
        """
        Add a job to the scheduler.

        Returns:
            Job ID
        """
        self._store.add(job)
        self._logger.info(f"Added job: {job.name} (next run: {job.next_run_time})")
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler."""
        job = self._store.remove(job_id)
        if job:
            self._logger.info(f"Removed job: {job.name}")
            return True
        return False

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        return self._store.get(job_id)

    def get_job_by_name(self, name: str) -> Optional[ScheduledJob]:
        """Get a job by name."""
        return self._store.get_by_name(name)

    def get_all_jobs(self) -> List[ScheduledJob]:
        """Get all scheduled jobs."""
        return self._store.get_all()

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        job = self._store.get(job_id)
        if job:
            job.pause()
            self._store.update(job)
            self._logger.info(f"Paused job: {job.name}")
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self._store.get(job_id)
        if job:
            job.resume()
            self._store.update(job)
            self._logger.info(f"Resumed job: {job.name}")
            return True
        return False

    def cancel_running_job(self, job_id: str) -> bool:
        """Cancel a currently running job."""
        return self._executor.cancel_job(job_id)

    async def run_job_now(self, job_id: str) -> Dict[str, Any]:
        """Run a job immediately (out of schedule)."""
        job = self._store.get(job_id)
        if not job:
            return {"status": "error", "error": "Job not found"}

        return await self._execute_job(job)

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        # Load persisted jobs
        self._store.load()

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self._logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._logger.info("Scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                # Get pending jobs
                pending_jobs = self._store.get_pending()

                # Execute pending jobs concurrently
                for job in pending_jobs:
                    if not self._executor.is_running(job.id):
                        asyncio.create_task(self._run_with_semaphore(job))

                # Wait for next check
                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _run_with_semaphore(self, job: ScheduledJob) -> None:
        """Run a job with concurrency limit."""
        async with self._semaphore:
            await self._execute_job(job)

    async def _execute_job(self, job: ScheduledJob) -> Dict[str, Any]:
        """Execute a job and update its state."""
        job.status = JobStatus.RUNNING
        self._store.update(job)

        # Trigger hooks
        await self._trigger_hook("job_started", job)

        self._logger.info(f"Executing job: {job.name}")

        # Execute with retries
        result = None
        success = False

        for attempt in range(job.max_retries + 1):
            result = await self._executor.execute(job)

            if result.get("status") != "error":
                success = True
                break

            if attempt < job.max_retries:
                self._logger.warning(
                    f"Job {job.name} failed (attempt {attempt + 1}), retrying..."
                )
                await asyncio.sleep(job.retry_delay)

        # Record result
        job.record_run(success, result)
        self._store.update(job)

        # Trigger hooks
        if success:
            await self._trigger_hook("job_completed", job, result)
            self._logger.info(f"Job completed: {job.name}")
        else:
            await self._trigger_hook("job_failed", job, result)
            self._logger.error(f"Job failed: {job.name} - {result.get('error')}")

        return result

    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a hook for scheduler events."""
        if event in self._hooks:
            self._hooks[event].append(callback)

    async def _trigger_hook(self, event: str, *args, **kwargs) -> None:
        """Trigger registered hooks."""
        for callback in self._hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                self._logger.error(f"Hook {event} error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        jobs = self._store.get_all()
        return {
            "running": self._running,
            "total_jobs": len(jobs),
            "enabled_jobs": len([j for j in jobs if j.enabled]),
            "pending_jobs": len(self._store.get_pending()),
            "check_interval": self._check_interval,
            "max_concurrent_jobs": self._max_concurrent_jobs,
        }

    def get_upcoming_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get upcoming job executions."""
        jobs = self._store.get_enabled()
        jobs_with_time = [
            (j.next_run_time, j) for j in jobs
            if j.next_run_time
        ]
        jobs_with_time.sort(key=lambda x: x[0])

        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat(),
                "module": job.module,
                "action": job.action,
            }
            for next_run, job in jobs_with_time[:limit]
        ]


# Global scheduler instance
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def reset_scheduler() -> None:
    """Reset the global scheduler (for testing)."""
    global _scheduler
    if _scheduler and _scheduler._running:
        asyncio.get_event_loop().run_until_complete(_scheduler.stop())
    _scheduler = None

"""
Core automation engine that orchestrates all automation modules.
"""

from typing import Any, Dict, List, Optional, Type
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

from .config import Config
from .logger import get_logger, AuditLogger


class AutomationModule:
    """Base class for all automation modules."""

    name: str = "base"
    description: str = "Base automation module"

    def __init__(self, config: Config, logger=None):
        self.config = config
        self.logger = logger or get_logger(f"module.{self.name}")

    def validate_config(self) -> bool:
        """Validate module-specific configuration."""
        return True

    def health_check(self) -> Dict[str, Any]:
        """Check module health and connectivity."""
        return {"status": "ok", "module": self.name}

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute an automation action."""
        raise NotImplementedError("Subclasses must implement execute()")


class AutomationEngine:
    """
    Main automation engine that coordinates all modules.
    Provides a unified interface for running automation tasks.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.logger = get_logger("engine")
        self.audit = AuditLogger()
        self._modules: Dict[str, AutomationModule] = {}
        self._executor = ThreadPoolExecutor(max_workers=10)

    def register_module(self, module_class: Type[AutomationModule]) -> None:
        """Register an automation module with the engine."""
        module = module_class(self.config)
        if module.validate_config():
            self._modules[module.name] = module
            self.logger.info(f"Registered module: {module.name}")
        else:
            self.logger.warning(f"Module {module.name} failed config validation")

    def get_module(self, name: str) -> Optional[AutomationModule]:
        """Get a registered module by name."""
        return self._modules.get(name)

    def list_modules(self) -> List[Dict[str, str]]:
        """List all registered modules."""
        return [
            {"name": m.name, "description": m.description}
            for m in self._modules.values()
        ]

    async def run_action(
        self,
        module_name: str,
        action: str,
        user: str = "system",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run an automation action on a specific module.

        Args:
            module_name: Name of the module to use
            action: Action to execute
            user: User initiating the action (for audit)
            **kwargs: Action-specific parameters

        Returns:
            Result dictionary with status and details
        """
        module = self._modules.get(module_name)
        if not module:
            return {
                "status": "error",
                "message": f"Module '{module_name}' not found"
            }

        self.logger.info(f"Executing {action} on {module_name}")

        try:
            result = await module.execute(action, **kwargs)

            self.audit.log_action(
                action=action,
                target=module_name,
                user=user,
                details=kwargs,
                success=result.get("status") == "success"
            )

            return result

        except Exception as e:
            self.logger.error(f"Action {action} failed: {e}")
            self.audit.log_action(
                action=action,
                target=module_name,
                user=user,
                details={"error": str(e), **kwargs},
                success=False
            )
            return {
                "status": "error",
                "message": str(e)
            }

    async def run_workflow(
        self,
        workflow: List[Dict[str, Any]],
        user: str = "system"
    ) -> List[Dict[str, Any]]:
        """
        Run a workflow consisting of multiple actions.

        Args:
            workflow: List of action definitions
            user: User initiating the workflow

        Returns:
            List of results for each action
        """
        results = []

        for step in workflow:
            module_name = step.get("module")
            action = step.get("action")
            params = step.get("params", {})

            result = await self.run_action(
                module_name=module_name,
                action=action,
                user=user,
                **params
            )

            results.append({
                "step": step,
                "result": result
            })

            # Stop on error unless continue_on_error is set
            if result.get("status") == "error" and not step.get("continue_on_error"):
                self.logger.error(f"Workflow stopped due to error in step: {step}")
                break

        return results

    def health_check_all(self) -> Dict[str, Any]:
        """Run health checks on all modules."""
        results = {}

        for name, module in self._modules.items():
            try:
                results[name] = module.health_check()
            except Exception as e:
                results[name] = {"status": "error", "message": str(e)}

        return results

    def shutdown(self) -> None:
        """Shutdown the engine and cleanup resources."""
        self._executor.shutdown(wait=True)
        self.logger.info("Automation engine shutdown complete")

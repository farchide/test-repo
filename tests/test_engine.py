"""
Tests for the automation engine.
"""

import pytest
import asyncio
from typing import Any, Dict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from onprem_automation.core.config import Config
from onprem_automation.core.engine import AutomationEngine, AutomationModule
from onprem_automation.core.logger import get_logger, AuditLogger


class MockModule(AutomationModule):
    """Mock module for testing."""
    name = "mock"
    description = "Mock automation module for testing"

    def __init__(self, config: Config, logger=None):
        super().__init__(config, logger)
        self.executed_actions = []

    def validate_config(self) -> bool:
        return True

    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "module": self.name}

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        self.executed_actions.append({"action": action, "kwargs": kwargs})
        if action == "fail":
            return {"status": "error", "message": "Intentional failure"}
        return {"status": "success", "action": action, "params": kwargs}


class FailingConfigModule(AutomationModule):
    """Module that fails config validation."""
    name = "failing_config"
    description = "Module that fails config validation"

    def validate_config(self) -> bool:
        return False


class TestAutomationModule:
    """Tests for AutomationModule base class."""

    def test_default_validate_config(self):
        """Test default validate_config returns True."""
        module = AutomationModule(Config())
        assert module.validate_config() is True

    def test_default_health_check(self):
        """Test default health_check returns ok status."""
        module = AutomationModule(Config())
        result = module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "base"


class TestAutomationEngine:
    """Tests for AutomationEngine."""

    def test_engine_initialization(self):
        """Test engine initializes correctly."""
        config = Config()
        engine = AutomationEngine(config)
        assert engine.config == config
        assert engine._modules == {}

    def test_register_module(self):
        """Test module registration."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        assert "mock" in engine._modules
        assert isinstance(engine._modules["mock"], MockModule)

    def test_register_module_failing_validation(self):
        """Test module with failing validation is not registered."""
        engine = AutomationEngine(Config())
        engine.register_module(FailingConfigModule)
        assert "failing_config" not in engine._modules

    def test_get_module(self):
        """Test getting registered module."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        module = engine.get_module("mock")
        assert module is not None
        assert module.name == "mock"

    def test_get_nonexistent_module(self):
        """Test getting non-existent module returns None."""
        engine = AutomationEngine(Config())
        module = engine.get_module("nonexistent")
        assert module is None

    def test_list_modules(self):
        """Test listing registered modules."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        modules = engine.list_modules()
        assert len(modules) == 1
        assert modules[0]["name"] == "mock"
        assert modules[0]["description"] == "Mock automation module for testing"

    @pytest.mark.asyncio
    async def test_run_action_success(self):
        """Test running successful action."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        result = await engine.run_action("mock", "test_action", param1="value1")
        assert result["status"] == "success"
        assert result["action"] == "test_action"
        assert result["params"]["param1"] == "value1"

    @pytest.mark.asyncio
    async def test_run_action_module_not_found(self):
        """Test running action on non-existent module."""
        engine = AutomationEngine(Config())
        result = await engine.run_action("nonexistent", "test_action")
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_run_action_failure(self):
        """Test running action that fails."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        result = await engine.run_action("mock", "fail")
        assert result["status"] == "error"
        assert "Intentional failure" in result["message"]

    @pytest.mark.asyncio
    async def test_run_workflow_success(self):
        """Test running successful workflow."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)

        workflow = [
            {"module": "mock", "action": "step1", "params": {}},
            {"module": "mock", "action": "step2", "params": {"key": "value"}}
        ]

        results = await engine.run_workflow(workflow)
        assert len(results) == 2
        assert results[0]["result"]["status"] == "success"
        assert results[1]["result"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_run_workflow_stops_on_error(self):
        """Test workflow stops on error by default."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)

        workflow = [
            {"module": "mock", "action": "step1", "params": {}},
            {"module": "mock", "action": "fail", "params": {}},
            {"module": "mock", "action": "step3", "params": {}}
        ]

        results = await engine.run_workflow(workflow)
        assert len(results) == 2  # Should stop after step 2
        assert results[1]["result"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_run_workflow_continue_on_error(self):
        """Test workflow continues with continue_on_error flag."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)

        workflow = [
            {"module": "mock", "action": "step1", "params": {}},
            {"module": "mock", "action": "fail", "params": {}, "continue_on_error": True},
            {"module": "mock", "action": "step3", "params": {}}
        ]

        results = await engine.run_workflow(workflow)
        assert len(results) == 3  # Should continue after step 2
        assert results[2]["result"]["status"] == "success"

    def test_health_check_all(self):
        """Test health check on all modules."""
        engine = AutomationEngine(Config())
        engine.register_module(MockModule)
        results = engine.health_check_all()
        assert "mock" in results
        assert results["mock"]["status"] == "ok"

    def test_shutdown(self):
        """Test engine shutdown."""
        engine = AutomationEngine(Config())
        engine.shutdown()
        # Should not raise any exceptions


class TestLogger:
    """Tests for logging functionality."""

    def test_get_logger(self):
        """Test getting a logger instance."""
        logger = get_logger("test")
        assert logger is not None
        assert logger.name == "test"

    def test_audit_logger(self):
        """Test AuditLogger initialization."""
        # This may fail if /var/log is not writable, but we test initialization
        try:
            audit = AuditLogger(audit_file="/tmp/test_audit.log")
            assert audit.logger is not None
        except PermissionError:
            pass  # Expected in restricted environments


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

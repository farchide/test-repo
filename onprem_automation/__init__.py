"""
On-Premises Automation System
A comprehensive Python framework for automating on-prem infrastructure operations.
"""

__version__ = "1.0.0"
__author__ = "Infrastructure Automation Team"

from .core.engine import AutomationEngine
from .core.config import Config
from .core.logger import get_logger

__all__ = ["AutomationEngine", "Config", "get_logger"]

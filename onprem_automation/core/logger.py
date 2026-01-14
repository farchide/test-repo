"""
Logging configuration for the automation system.
Provides structured logging with support for multiple outputs.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    json_format: bool = False,
    colored: bool = True
) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (usually module name)
        level: Logging level
        log_file: Optional file path for logging
        json_format: Use JSON formatting for file output
        colored: Use colored output for console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if colored and sys.stdout.isatty():
        console_format = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))

        logger.addHandler(file_handler)

    return logger


class AuditLogger:
    """
    Specialized logger for audit trail of automation actions.
    Records all changes made by the automation system.
    """

    def __init__(self, audit_file: str = "/var/log/onprem_automation/audit.log"):
        self.logger = get_logger(
            'audit',
            log_file=audit_file,
            json_format=True
        )

    def log_action(
        self,
        action: str,
        target: str,
        user: str,
        details: dict,
        success: bool = True
    ) -> None:
        """Log an automation action for audit purposes."""
        record = logging.LogRecord(
            name='audit',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg=f"{action} on {target}",
            args=(),
            exc_info=None
        )
        record.extra_data = {
            'action': action,
            'target': target,
            'user': user,
            'details': details,
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.logger.handle(record)

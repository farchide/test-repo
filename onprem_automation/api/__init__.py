"""
REST API Package

Provides FastAPI-based REST API with:
- OpenAPI/Swagger documentation
- JWT authentication
- WebSocket support
- Rate limiting
"""

from .main import create_app, app
from .auth import get_current_user, require_permission

__all__ = [
    "create_app",
    "app",
    "get_current_user",
    "require_permission",
]

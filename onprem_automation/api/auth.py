"""
Authentication & Authorization

Provides:
- JWT token authentication
- RBAC permission checking
- API key support
- SSO integration hooks
"""

from typing import Optional, List, Callable
from datetime import datetime, timedelta
from functools import wraps
import os
import hashlib
import logging

# Try imports
try:
    from fastapi import HTTPException, Security, Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Security schemes
if FASTAPI_AVAILABLE:
    bearer_scheme = HTTPBearer(auto_error=False)
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_access_token(
    user_id: str,
    username: str,
    roles: List[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT is not installed. Run: pip install pyjwt")

    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": user_id,
        "username": username,
        "roles": roles or [],
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT is not installed")

    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT is not installed")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def hash_password(password: str) -> str:
    """Hash password with SHA-256 (use bcrypt in production)."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password hash."""
    return hash_password(plain_password) == hashed_password


class CurrentUser:
    """Current user context."""
    def __init__(
        self,
        id: str,
        username: str,
        roles: List[str] = None,
        permissions: List[str] = None,
        is_superuser: bool = False,
    ):
        self.id = id
        self.username = username
        self.roles = roles or []
        self.permissions = permissions or []
        self.is_superuser = is_superuser

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        if self.is_superuser:
            return True
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return role in self.roles


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme) if FASTAPI_AVAILABLE else None,
    api_key: str = Security(api_key_header) if FASTAPI_AVAILABLE else None,
) -> CurrentUser:
    """
    Get current user from JWT token or API key.

    Usage:
        @app.get("/protected")
        async def protected_route(user: CurrentUser = Depends(get_current_user)):
            return {"user": user.username}
    """
    # Try JWT token first
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        # Load user permissions from database
        from ..database.session import DatabaseSession
        from ..database.models import User

        with DatabaseSession() as session:
            user = session.query(User).filter(User.id == payload["sub"]).first()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            if not user.is_active:
                raise HTTPException(status_code=401, detail="User is inactive")

            permissions = []
            for role in user.roles:
                for perm in role.permissions:
                    permissions.append(perm.name)

            return CurrentUser(
                id=user.id,
                username=user.username,
                roles=[r.name for r in user.roles],
                permissions=list(set(permissions)),
                is_superuser=user.is_superuser,
            )

    # Try API key
    if api_key:
        return await _validate_api_key(api_key)

    raise HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme) if FASTAPI_AVAILABLE else None,
    api_key: str = Security(api_key_header) if FASTAPI_AVAILABLE else None,
) -> Optional[CurrentUser]:
    """Get current user if authenticated, None otherwise."""
    try:
        return await get_current_user(credentials, api_key)
    except HTTPException:
        return None


async def _validate_api_key(api_key: str) -> CurrentUser:
    """Validate API key and return user."""
    # TODO: Implement API key validation from database
    # For now, check against environment variable
    valid_key = os.environ.get("API_KEY")
    if valid_key and api_key == valid_key:
        return CurrentUser(
            id="api-user",
            username="api-user",
            roles=["api"],
            permissions=["*"],
            is_superuser=True,
        )

    raise HTTPException(status_code=401, detail="Invalid API key")


def require_permission(permission: str):
    """
    Decorator/dependency to require specific permission.

    Usage:
        @app.post("/jobs")
        async def create_job(
            job: JobCreate,
            _: None = Depends(require_permission("job:create"))
        ):
            ...
    """
    async def permission_checker(
        user: CurrentUser = Depends(get_current_user) if FASTAPI_AVAILABLE else None
    ):
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if not user.has_permission(permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required"
            )

        return user

    return Depends(permission_checker) if FASTAPI_AVAILABLE else None


def require_role(role: str):
    """Decorator/dependency to require specific role."""
    async def role_checker(
        user: CurrentUser = Depends(get_current_user) if FASTAPI_AVAILABLE else None
    ):
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if not user.has_role(role) and not user.is_superuser:
            raise HTTPException(
                status_code=403,
                detail=f"Role required: {role}"
            )

        return user

    return Depends(role_checker) if FASTAPI_AVAILABLE else None


# ==================== Login/Logout ====================

async def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate user and return tokens."""
    from ..database.session import DatabaseSession
    from ..database.models import User

    with DatabaseSession() as session:
        user = session.query(User).filter(User.username == username).first()

        if not user:
            return None

        if not verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        # Update last login
        user.last_login = datetime.utcnow()

        roles = [r.name for r in user.roles]

        return {
            "access_token": create_access_token(user.id, user.username, roles),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": roles,
            }
        }


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh access token using refresh token."""
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    from ..database.session import DatabaseSession
    from ..database.models import User

    with DatabaseSession() as session:
        user = session.query(User).filter(User.id == payload["sub"]).first()

        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        roles = [r.name for r in user.roles]

        return {
            "access_token": create_access_token(user.id, user.username, roles),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

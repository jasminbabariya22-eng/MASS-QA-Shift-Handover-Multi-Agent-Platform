from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import logfire

from app.config import settings


class UserRole(str, Enum):
    USER = "USER"
    CONSOLE_OPERATOR = "CONSOLE_OPERATOR"
    FIELD_OPERATOR = "FIELD_OPERATOR"
    INCOMING_OPERATOR = "INCOMING_OPERATOR"
    SUPERVISOR = "SUPERVISOR"
    SHIFT_SUPERVISOR = "SHIFT_SUPERVISOR"
    OPERATIONS_ENGINEER = "OPERATIONS_ENGINEER"
    MAINTENANCE_LEAD = "MAINTENANCE_LEAD"
    HSE_REPRESENTATIVE = "HSE_REPRESENTATIVE"
    ADMIN = "ADMIN"


ROLE_HIERARCHY = {
    UserRole.USER: 1,
    UserRole.FIELD_OPERATOR: 1,
    UserRole.CONSOLE_OPERATOR: 1,
    UserRole.INCOMING_OPERATOR: 1,
    UserRole.SUPERVISOR: 2,
    UserRole.SHIFT_SUPERVISOR: 2,
    UserRole.OPERATIONS_ENGINEER: 2,
    UserRole.MAINTENANCE_LEAD: 2,
    UserRole.HSE_REPRESENTATIVE: 2,
    UserRole.ADMIN: 3
}


class UserPayload(BaseModel):
    user_id: str
    username: str
    role: UserRole = UserRole.USER
    session_id: Optional[str] = None


security_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: str,
    username: str,
    role: str = "USER",
    session_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a signed JWT access token for API authentication.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "session_id": session_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }

    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> UserPayload:
    """
    Decode and validate a signed JWT token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        username = payload.get("username", "user")
        role_str = payload.get("role", "USER").upper()
        role = UserRole(role_str) if role_str in UserRole._value2member_map_ else UserRole.USER
        session_id = payload.get("session_id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject claim."
            )

        return UserPayload(
            user_id=user_id,
            username=username,
            role=role,
            session_id=session_id
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired."
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}"
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> UserPayload:
    """
    FastAPI dependency for authenticating user via Bearer JWT.
    Supports development mode bypass when AUTH_REQUIRED=false.
    """
    if credentials is not None:
        return decode_access_token(credentials.credentials)

    # If Auth is required and no credentials were provided
    if settings.AUTH_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authentication token in Authorization header."
        )

    # Development fallback
    return UserPayload(
        user_id="dev-user-001",
        username="Development User",
        role=UserRole.ADMIN,
        session_id="dev-session-default"
    )


def require_role(min_role: UserRole | str):
    """
    Authorization dependency ensuring current user meets minimum required role level.
    """
    target_role = UserRole(min_role) if isinstance(min_role, str) else min_role

    def role_checker(current_user: UserPayload = Depends(get_current_user)) -> UserPayload:
        user_level = ROLE_HIERARCHY.get(current_user.role, 1)
        required_level = ROLE_HIERARCHY.get(target_role, 1)

        if user_level < required_level:
            logfire.warning(f"Unauthorized role access attempt: {current_user.user_id} ({current_user.role}) -> required {target_role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires '{target_role.value}' role."
            )
        return current_user

    return role_checker

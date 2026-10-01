"""Centralized session authentication and password security helpers."""

from dataclasses import dataclass
import logging
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from starlette.responses import RedirectResponse
from werkzeug.security import check_password_hash, generate_password_hash

from app.database.repositories.users import get_user_by_id, get_user_by_provider

logger = logging.getLogger(__name__)

from enum import Enum

class SessionKeys(str, Enum):
    USER_ID = "user_id"
    PROVIDER_ID = "provider_id"
    PROVIDER = "provider"

@dataclass(frozen=True)
class CurrentUser:
    """Safe user data exposed to routes and templates."""

    id: int
    username: str
    email: str | None = None
    auth_provider: str = "local"


def hash_password(password: str) -> str:
    """Hash a password with Werkzeug's supported password-hashing implementation."""
    return generate_password_hash(password, method="scrypt")


def verify_password(password: str, password_hash: str) -> bool:
    """Safely verify a plaintext password against a stored hash."""
    try:
        return check_password_hash(password_hash, password)
    except (TypeError, ValueError):
        return False


def user_from_row(row) -> CurrentUser | None:
    """Convert a database row to the safe current-user representation."""
    if row is None:
        return None
    return CurrentUser(
        id=int(row["id"]),
        username=str(row["username"]),
        email=row["email"] if "email" in row else None,
        auth_provider=row["auth_provider"] if "auth_provider" in row else "local",
    )


def get_current_user(request: Request) -> CurrentUser | None:
    """Resolve the session user, returning None for anonymous requests."""
    raw_user_id = request.session.get(SessionKeys.USER_ID)
    provider_id = request.session.get(SessionKeys.PROVIDER_ID) or None
    provider = request.session.get(SessionKeys.PROVIDER) or None
    try:
        user_id = int(raw_user_id) if raw_user_id else None
    except (TypeError, ValueError):
        return None
    
    try:
        if provider and provider_id and provider!="local":
            return user_from_row(get_user_by_provider(provider, provider_id))
        return user_from_row(get_user_by_id(user_id))
    except Exception:
        logger.error("Unable to resolve current session user", exc_info=True)
        return None


def get_current_user_id(request: Request) -> int | None:
    """Return the authenticated database ID or None for anonymous visitors."""
    try:
        raw_user_id = request.session.get(SessionKeys.USER_ID)
        return int(raw_user_id) if raw_user_id is not None else None
    except (TypeError, ValueError):
        return None


def require_current_user(request: Request) -> CurrentUser:
    """Require an authenticated user for an API route."""
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def login_session(request: Request, user_id: int, provider_id=None, provider=None) -> None:
    """Rotate the session and store only the stable local user ID."""
    request.session.clear()
    request.session[SessionKeys.USER_ID] = int(user_id)
    request.session[SessionKeys.PROVIDER] = provider or None
    request.session[SessionKeys.PROVIDER_ID] = provider_id or None


def logout_session(request: Request) -> None:
    """Invalidate all authentication session state."""
    request.session.clear()


def safe_next_path(value: str | None, fallback: str = "/") -> str:
    """Allow only local absolute paths for post-login redirects."""
    if not value:
        return fallback
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return fallback
    return value


def login_redirect(request: Request) -> RedirectResponse:
    """Redirect browsers to login while preserving a safe internal path."""
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    return RedirectResponse(f"/login?next={safe_next_path(path)}", status_code=303)

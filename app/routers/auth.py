"""Local session authentication and Google OAuth routes."""

import logging
import re
from urllib.parse import urlencode
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from werkzeug.exceptions import BadRequest

from app.core import config
from app.core.security import hash_password, login_session, logout_session, safe_next_path, verify_password
from app.database.repositories.users import create_google_user, create_local_user, get_user_by_email, get_user_by_provider, get_user_by_username

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def _valid_username(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", value))


def _valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse(request=request, name="signup.html", context={"error": None, "user_authenticated": False})


@router.post("/signup")
async def signup(request: Request, username: str = Form(...), email: str = Form(""), password: str = Form(...)):
    username, email = username.strip(), email.strip().lower() or None
    error = "Enter a valid username, email, and password." if not _valid_username(username) or (email and not _valid_email(email)) or len(password) < 8 else None
    if error:
        return templates.TemplateResponse(request=request, name="signup.html", context={"error": error, "user_authenticated": False}, status_code=400)
    try:
        if get_user_by_username(username) or (email and get_user_by_email(email)):
            return templates.TemplateResponse(request=request, name="signup.html", context={"error": "Account already exists.", "user_authenticated": False}, status_code=400)
        user_id = create_local_user(username, hash_password(password), email)
        login_session(request, user_id)
        return RedirectResponse("/", status_code=303)
    except Exception:
        logger.error("Local account creation failed", exc_info=True)
        return templates.TemplateResponse(request=request, name="signup.html", context={"error": "Unable to create that account.", "user_authenticated": False}, status_code=400)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None, "next": safe_next_path(next), "google_enabled": bool(config.GOOGLE_CLIENT_ID), "user_authenticated": False})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    row = get_user_by_username(username.strip())
    if row is None or row["auth_provider"] != "local" or not verify_password(password, row["hash"]):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password.", "next": safe_next_path(next), "google_enabled": bool(config.GOOGLE_CLIENT_ID), "user_authenticated": False}, status_code=400)
    login_session(request, int(row["id"]))
    return RedirectResponse(safe_next_path(next), status_code=303)


@router.post("/logout")
async def logout(request: Request):
    logout_session(request)
    return RedirectResponse("/", status_code=303)


_oauth = None


def _get_oauth() -> object:
    """Return a shared OAuth client registered once with the Google provider."""
    global _oauth
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth
        _oauth = OAuth()
        _oauth.register(
            name="google",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    return _oauth


@router.get("/auth/google")
async def google_login(request: Request):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return RedirectResponse("/login?error=google_unavailable", status_code=303)
    oauth = _get_oauth()
    return await oauth.google.authorize_redirect(request, config.GOOGLE_REDIRECT_URI)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return RedirectResponse("/login?error=google_unavailable", status_code=303)
    oauth = _get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
        provider_id, email = userinfo.get("sub"), userinfo.get("email")
        if not provider_id:
            logger.error("Google callback missing subject")
            return RedirectResponse("/login?error=google_failed", status_code=303)
        
        row = get_user_by_provider("google", provider_id)
        
        # 2. Fallback check by email (only if verified by Google)
        if not row and email and userinfo.get("email_verified"):
            row = get_user_by_email(email)
            if row and row["auth_provider"] != "google":
                # Security boundary: Prevent local accounts from being highjacked via simple email match
                logger.warning("Google login email collision with local provider for email: %s", email)
                return RedirectResponse("/login?error=account_collision", status_code=303)

        # 1. Get the user's name or email, or generate a default one
        raw_username = userinfo.get("name") or email or f"google_{provider_id[:12]}"

        # 2. Make it safe: Replace spaces/special chars with underscores, lower it, and crop to 32 chars max
        safe_username = re.sub(r"[^A-Za-z0-9_.-]", "_", raw_username)[:32]    

        user_id = int(row["id"]) if row else create_google_user(safe_username, email, provider_id)
        login_session(request, user_id, provider_id=provider_id, provider="google")
        return RedirectResponse("/", status_code=303)
    except Exception: 
        logger.error("Google authentication failed", exc_info=True)
        return RedirectResponse("/login?error=google_failed", status_code=303)
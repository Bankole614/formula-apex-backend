import time
from typing import Optional
import jwt
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def verify_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    auth: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> bool:
    """
    Enforce administrator privileges for sensitive endpoints (e.g. music upload, track publishing management).
    Accepts either an 'X-Admin-Key' header or 'Bearer <token>'.
    """
    token = None
    if x_admin_key:
        token = x_admin_key.strip()
    elif auth and auth.credentials:
        token = auth.credentials.strip()

    if not token or token != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required. Invalid or missing X-Admin-Key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


def create_player_token(user_id: str, driver_name: str, expires_in_seconds: int = 86400 * 30) -> str:
    """
    Generate a signed JWT token representing a verified player identity.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "name": driver_name,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def verify_player_token(token: str) -> Optional[dict]:
    """
    Decode and verify a player JWT token. Returns payload or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception:
        return None


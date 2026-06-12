from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

_bearer = HTTPBearer()


def _decode_payload(credentials: HTTPAuthorizationCredentials) -> dict:
    try:
        return jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def _extract_sub(payload: dict) -> UUID:
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid moderator ID in token") from exc


async def get_current_moderator_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    return _extract_sub(_decode_payload(credentials))


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    payload = _decode_payload(credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return _extract_sub(payload)

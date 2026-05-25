from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

_bearer = HTTPBearer()


async def get_current_moderator_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid moderator ID in token") from exc

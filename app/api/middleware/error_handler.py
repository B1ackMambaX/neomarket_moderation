from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import DomainException


async def domain_exception_handler(
    request: Request,
    exc: DomainException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": str(exc), "details": None},
    )

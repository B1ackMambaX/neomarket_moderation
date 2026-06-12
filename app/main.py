from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.error_handler import domain_exception_handler
from app.api.v1.routers import b2b_events, blocking_reasons, queue, tickets
from app.core.config import ALLOWED_ORIGINS, settings
from app.core.database import engine
from app.domain.exceptions import DomainException


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="NeoMarket Moderation API",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(DomainException, domain_exception_handler)

app.include_router(tickets.router, prefix="/api/v1")
app.include_router(queue.router, prefix="/api/v1")
app.include_router(b2b_events.router, prefix="/api/v1")
app.include_router(blocking_reasons.router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}

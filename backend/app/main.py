"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import init_db
from .ratelimit import RateLimitMiddleware
from .routers import ai, auth, files, review, sign, signrequests, tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pdfdesk")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.jwt_secret == "change-me" and settings.environment == "production":
        log.warning("JWT_SECRET is not set - set a long random value in .env before going live!")
    yield


app = FastAPI(title="PDFDesk API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, files.router, tools.router, sign.router, signrequests.router, review.router, ai.router):
    app.include_router(r)


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one friendly sentence (never echo the submitted values)."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    return JSONResponse({"detail": f"Invalid {field}: {first.get('msg', 'invalid value')}."}, status_code=422)


@app.exception_handler(Exception)
async def _unhandled(_request: Request, exc: Exception):
    log.error("Unhandled error: %s", exc.__class__.__name__, exc_info=exc)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai": settings.ai_enabled}

"""FastAPI application entry."""
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import agent, quiz
from app.core.config import get_settings
from app.db.session import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.web.routes import router as web_router

settings = get_settings()


# ---- Logging: structured JSON sink with request_id binding ----
logger.remove()
logger.add(
    sys.stdout,
    serialize=settings.environment != "dev",
    level="DEBUG" if settings.debug else "INFO",
    backtrace=False,
    diagnose=False,
)


# ---- Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.environment != "dev":
        start_scheduler()
    logger.info("familysafety started", extra={"env": settings.environment})
    yield
    stop_scheduler()
    logger.info("familysafety stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    # Always False at the framework level; debug UI is opt-in via separate route.
    debug=False,
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    )


# ---- Middleware: request_id + access log ----
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = rid
    with logger.contextualize(request_id=rid, path=request.url.path, method=request.method):
        try:
            response = await call_next(request)
        except Exception as exc:  # last-resort safety net
            logger.exception("unhandled exception")
            response = JSONResponse(
                {"detail": "internal server error"},
                status_code=500,
            )
        response.headers["X-Request-ID"] = rid
        logger.info(
            "request handled",
            extra={"status_code": response.status_code},
        )
        return response


# ---- Global exception handlers ----
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # For dashboard routes (anything under /web or /) render friendly HTML;
    # otherwise return JSON.
    if _wants_html(request) and exc.status_code in (403, 404, 500):
        try:
            tmpl = _templates_for_errors()
            return tmpl.TemplateResponse(
                request,
                f"errors/{exc.status_code}.html",
                {
                    "request": request,
                    "path": request.url.path,
                    "request_id": getattr(request.state, "request_id", ""),
                    "status_code": exc.status_code,
                },
                status_code=exc.status_code,
            )
        except Exception:
            logger.exception("error page render failed")
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "")
    logger.exception("unhandled error rid={}", rid)
    if _wants_html(request):
        try:
            tmpl = _templates_for_errors()
            return tmpl.TemplateResponse(
                request,
                "errors/500.html",
                {"request": request, "request_id": rid},
                status_code=500,
            )
        except Exception:
            logger.exception("500 page render failed")
    return JSONResponse(
        {"detail": "internal server error"},
        status_code=500,
    )


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and request.url.path.startswith("/web")


def _templates_for_errors():
    """Lazy import + lazy template engine to avoid circular imports."""
    from pathlib import Path
    from fastapi.templating import Jinja2Templates
    import jinja2
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "web" / "templates")),
        autoescape=True,
        enable_async=False,
    )
    from app.i18n import t as _i18n_t
    env.globals["t"] = _i18n_t
    return Jinja2Templates(env=env)


# ---- Static files ----
STATIC_DIR = Path(__file__).parent / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---- Health checks ----
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": settings.app_version}


@app.get("/readyz")
async def readyz() -> dict:
    from sqlalchemy import text
    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        logger.exception("readyz db check failed")
        return {"status": "not_ready"}


app.include_router(agent.router, prefix=settings.api_v1_prefix)
app.include_router(quiz.router, prefix=settings.api_v1_prefix)
app.include_router(web_router)
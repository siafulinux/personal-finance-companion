"""FastAPI application factory with security headers and CSRF protection."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.ai.provider import ai_status
from app.api import accounts, auth, bills, budgets, categories, imports, insights, transactions
from app.config import settings
from app.database.base import SessionLocal
from app.logging_config import configure_logging
from app.security.tokens import tokens_match
from app.services.errors import DomainError

API_PREFIX = "/api/v1"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PATHS = {f"{API_PREFIX}/auth/login", f"{API_PREFIX}/auth/register"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


def create_app() -> FastAPI:
    settings.validate_runtime()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0-phase1",
        description=(
            "Local-first personal finance API. All endpoints except health and meta "
            "require authentication. Financial arithmetic is deterministic and "
            "server-side."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # CSRF protection for cookie-authenticated state changes.
        if (
            request.method in UNSAFE_METHODS
            and request.url.path not in CSRF_EXEMPT_PATHS
            and request.cookies.get(settings.session_cookie_name)
            and not request.headers.get("authorization")
        ):
            header = request.headers.get("x-csrf-token")
            cookie = request.cookies.get(settings.csrf_cookie_name)
            if not tokens_match(header, cookie):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid. Refresh and try again."},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000"
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "extra": exc.details},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Please check the highlighted fields.", "errors": exc.errors()},
        )

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(accounts.router, prefix=API_PREFIX)
    app.include_router(categories.router, prefix=API_PREFIX)
    app.include_router(transactions.router, prefix=API_PREFIX)
    app.include_router(imports.router, prefix=API_PREFIX)
    app.include_router(budgets.router, prefix=API_PREFIX)
    app.include_router(bills.router, prefix=API_PREFIX)
    app.include_router(insights.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health() -> dict:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "environment": settings.environment}

    @app.get(f"{API_PREFIX}/meta", tags=["meta"])
    def meta() -> dict:
        from app.models.enums import AccountType, CategoryKind, Frequency, IncomeFrequency, TransactionType
        from app.services.categories import DEFAULT_CATEGORIES

        return {
            "app_name": settings.app_name,
            "version": "phase1",
            "currency": "USD",
            "account_types": [t.value for t in AccountType],
            "transaction_types": [t.value for t in TransactionType],
            "categories": [
                {"name": name, "color": color, "icon": icon}
                for name, color, icon in DEFAULT_CATEGORIES
            ],
            "bill_frequencies": [f.value for f in Frequency],
            "income_frequencies": [f.value for f in IncomeFrequency],
            "category_kinds": [k.value for k in CategoryKind],
            "default_timezone": settings.default_timezone,
            "safe_to_spend_horizon_days": settings.default_safe_to_spend_horizon_days,
            "max_horizon_days": settings.max_safe_to_spend_horizon_days,
            "ai": ai_status(),
            "phase": 1,
        }

    return app


app = create_app()

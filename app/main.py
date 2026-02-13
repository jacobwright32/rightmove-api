import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from .config import CORS_ORIGINS, ENABLE_ADMIN, LOG_LEVEL
from .database import Base, _migrate_db, engine
from .rate_limit import limiter
from .routers import analytics, enrichment, modelling, properties, scraper

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Migrate existing databases, then create any new tables
_migrate_db()
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="UK House Prices API",
    description="On-demand scraping and querying of UK house price data.",
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

logger = logging.getLogger(__name__)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        logger.info(
            "%s %s %d %.3fs",
            request.method, request.url.path, response.status_code, time.time() - start,
        )
    return response


app.include_router(scraper.router, prefix="/api/v1")
app.include_router(properties.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(analytics.postcode_router, prefix="/api/v1")
app.include_router(enrichment.router, prefix="/api/v1")
app.include_router(enrichment.crime_router, prefix="/api/v1")
app.include_router(enrichment.flood_router, prefix="/api/v1")
app.include_router(enrichment.planning_router, prefix="/api/v1")
app.include_router(enrichment.listing_router, prefix="/api/v1")
app.include_router(enrichment.bulk_router, prefix="/api/v1")
app.include_router(modelling.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    """Health check endpoint — verifies DB connectivity."""
    from .database import SessionLocal
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": app.version,
        "database": db_status,
    }


@app.get("/")
def root():
    return {
        "message": "UK House Prices API",
        "docs": "/docs",
    }


if ENABLE_ADMIN:
    @app.post("/api/v1/admin/reset-database")
    def reset_database():
        """Drop all data and recreate tables. Irreversible."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        return {"message": "Database reset successfully. All data has been deleted."}

    @app.post("/api/v1/admin/shutdown")
    def shutdown():
        """Gracefully shut down the server."""
        import signal

        os.kill(os.getpid(), signal.SIGTERM)
        return {"message": "Server shutting down..."}


# Serve React production build if it exists (with SPA fallback)
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    from fastapi.responses import FileResponse

    _index_html = os.path.join(_frontend_dist, "index.html")

    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    _frontend_dist_real = os.path.realpath(_frontend_dist)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback — serve index.html for all non-API routes."""
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file_path = os.path.realpath(os.path.join(_frontend_dist, full_path))
        if not file_path.startswith(_frontend_dist_real):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(_index_html)

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import CORS_ORIGINS, LOG_LEVEL, RATE_LIMIT_DEFAULT
from .database import Base, engine, _migrate_db
from .routers import analytics, properties, scraper

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Migrate existing databases, then create any new tables
_migrate_db()
Base.metadata.create_all(bind=engine)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])

app = FastAPI(
    title="Rightmove House Prices API",
    description="On-demand scraping and querying of Rightmove house price data.",
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
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scraper.router, prefix="/api/v1")
app.include_router(properties.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")


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
        "message": "Rightmove House Prices API",
        "docs": "/docs",
    }


# Serve React production build if it exists
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")

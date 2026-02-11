"""Application configuration loaded from environment variables and secrets."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Secrets directory (gitignored — stores API keys as individual files)
SECRETS_DIR: Path = Path(__file__).resolve().parent.parent / "secrets"


def _read_secret(name: str, default: str = "") -> str:
    """Read a secret from secrets/ file, falling back to env var then default."""
    env_val = os.getenv(name.upper())
    if env_val:
        return env_val
    secret_file = SECRETS_DIR / name.lower()
    if secret_file.is_file():
        return secret_file.read_text().strip()
    return default


# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rightmove.db")

# CORS
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# Scraper
SCRAPER_REQUEST_TIMEOUT: int = int(os.getenv("SCRAPER_REQUEST_TIMEOUT", "30"))
SCRAPER_RETRY_ATTEMPTS: int = int(os.getenv("SCRAPER_RETRY_ATTEMPTS", "3"))
SCRAPER_RETRY_BACKOFF: float = float(os.getenv("SCRAPER_RETRY_BACKOFF", "1.0"))
SCRAPER_DELAY_BETWEEN_REQUESTS: float = float(os.getenv("SCRAPER_DELAY_BETWEEN_REQUESTS", "0.25"))
SCRAPER_FRESHNESS_DAYS: int = int(os.getenv("SCRAPER_FRESHNESS_DAYS", "7"))

# EPC API (register free at https://epc.opendatacommunities.org/)
EPC_API_EMAIL: str = _read_secret("epc_api_email")
EPC_API_KEY: str = _read_secret("epc_api_key")

# Listing freshness (how long before re-checking if a property is for sale)
LISTING_FRESHNESS_HOURS: int = int(os.getenv("LISTING_FRESHNESS_HOURS", "24"))

# Rate limiting
RATE_LIMIT_SCRAPE: str = os.getenv("RATE_LIMIT_SCRAPE", "30/minute")
RATE_LIMIT_DEFAULT: str = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")

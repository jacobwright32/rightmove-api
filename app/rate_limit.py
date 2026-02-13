"""Shared rate limiter with reverse-proxy awareness (X-Forwarded-For)."""

from fastapi import Request
from slowapi import Limiter

from .config import RATE_LIMIT_DEFAULT


def get_real_ip(request: Request) -> str:
    """Extract client IP, preferring X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(key_func=get_real_ip, default_limits=[RATE_LIMIT_DEFAULT])

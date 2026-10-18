"""Per-IP fixed-window rate limiting. Uses Redis when available, else an in-memory counter."""
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings


class _MemoryCounter:
    def __init__(self):
        self.counts: dict[str, int] = defaultdict(int)
        self.lock = Lock()
        self.window = 0

    def hit(self, key: str, window: int) -> int:
        with self.lock:
            if window != self.window:  # new minute: reset everything
                self.counts.clear()
                self.window = window
            self.counts[key] += 1
            return self.counts[key]


class RateLimiter:
    def __init__(self):
        self.memory = _MemoryCounter()
        self.redis = None
        s = get_settings()
        if s.job_mode == "queue":
            try:
                import redis

                self.redis = redis.Redis.from_url(s.redis_url, socket_timeout=0.5)
                self.redis.ping()
            except Exception:
                self.redis = None

    def hit(self, key: str) -> int:
        window = int(time.time() // 60)
        if self.redis is not None:
            try:
                rkey = f"rl:{key}:{window}"
                pipe = self.redis.pipeline()
                pipe.incr(rkey)
                pipe.expire(rkey, 70)
                return int(pipe.execute()[0])
            except Exception:
                pass  # fall back to memory if Redis hiccups
        return self.memory.hit(key, window)


def client_ip(request: Request) -> str:
    # Nginx sets X-Real-IP; trust it only because the app is only reachable through the proxy.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


class RateLimitMiddleware(BaseHTTPMiddleware):
    AUTH_PATHS = ("/api/auth/login", "/api/auth/signup", "/api/auth/forgot-password", "/api/auth/reset-password")

    def __init__(self, app):
        super().__init__(app)
        self.limiter = RateLimiter()

    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            ip = client_ip(request)
            is_auth = path in self.AUTH_PATHS
            limit = s.rate_limit_auth_per_minute if is_auth else s.rate_limit_per_minute
            count = self.limiter.hit(f"{'auth' if is_auth else 'api'}:{ip}")
            if count > limit:
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a minute and try again."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)

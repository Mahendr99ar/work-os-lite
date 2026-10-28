"""A small in-memory rate limiter.

Free LLM keys have daily quotas, and a public demo link can be hit by anyone,
so the expensive endpoints get a per-user or per-IP limit.

The counts live in this process's memory. With one server (the free hosting
setup) that is enough. With several servers you would move this to Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self.hits[key]
        while hits and now - hits[0] > self.window:  # forget hits older than the window
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = int(self.window - (now - hits[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many requests. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)

    def reset(self) -> None:
        self.hits.clear()


login_limiter = RateLimiter("login", limit=10, window_seconds=60)
# Per account, so a forged X-Forwarded-For header cannot be used to keep guessing one password.
account_login_limiter = RateLimiter("account_login", limit=10, window_seconds=300)
demo_limiter = RateLimiter("demo", limit=5, window_seconds=3600)
ask_limiter = RateLimiter("ask", limit=20, window_seconds=60)
plan_limiter = RateLimiter("plan", limit=6, window_seconds=60)

ALL_LIMITERS = (login_limiter, account_login_limiter, demo_limiter, ask_limiter, plan_limiter)


def client_ip(request: Request) -> str:
    # Render sits behind a proxy. Render staff say the first entry is the real client, but a
    # client can also send this header itself, so per-IP limits are a soft guard only.
    # Login is also limited per account (account_login_limiter), which does not depend on IPs.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

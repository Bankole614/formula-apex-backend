import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status
from ..config import settings


class SlidingWindowRateLimiter:
    """
    Lightweight, thread-safe in-memory sliding-window rate limiter for FastAPI routes.
    Keys are evaluated per client IP + route path.
    """

    def __init__(self, times: int = 30, seconds: int = 60):
        self.times = times
        self.seconds = seconds
        self._history: Dict[str, List[float]] = defaultdict(list)

    async def __call__(self, request: Request):
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        now = time.time()
        window_start = now - self.seconds

        # Prune timestamps older than window
        timestamps = [ts for ts in self._history[key] if ts > window_start]
        if len(timestamps) >= self.times:
            retry_after = int(self.seconds - (now - timestamps[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({self.times} req/{self.seconds}s). Try again in {retry_after}s.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        timestamps.append(now)
        self._history[key] = timestamps


# Common pre-configured rate limit dependencies
rate_limit_submissions = SlidingWindowRateLimiter(times=15, seconds=60)  # Laps, track uploads
rate_limit_reactions = SlidingWindowRateLimiter(times=30, seconds=60)    # Likes, votes
rate_limit_lobby = SlidingWindowRateLimiter(times=20, seconds=60)        # Room creations


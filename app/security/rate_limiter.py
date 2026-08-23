import time
from typing import Dict, List, Tuple, Optional
from fastapi import Request, HTTPException, status
import logfire

from app.config import settings


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Tracks timestamps of requests per client key (IP or user_id) within 60-second windows.
    """

    def __init__(self):
        self._records: Dict[str, List[float]] = {}

    def is_allowed(self, key: str, max_requests: int, window_seconds: float = 60.0) -> Tuple[bool, int, float]:
        """
        Check if request is allowed.
        Returns:
            (allowed: bool, remaining: int, retry_after: float)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, max_requests, 0.0

        now = time.time()
        window_start = now - window_seconds

        # Get or create timestamp list
        timestamps = self._records.get(key, [])
        
        # Prune timestamps older than window
        timestamps = [ts for ts in timestamps if ts > window_start]

        if len(timestamps) < max_requests:
            timestamps.append(now)
            self._records[key] = timestamps
            remaining = max_requests - len(timestamps)
            return True, remaining, 0.0
        else:
            self._records[key] = timestamps
            # Oldest timestamp in window dictates retry-after
            oldest = timestamps[0] if timestamps else now
            retry_after = max(1.0, round((oldest + window_seconds) - now, 1))
            return False, 0, retry_after

    def reset(self):
        """Clear all rate limit tracking records."""
        self._records.clear()


# Global in-memory limiter instance
rate_limiter = SlidingWindowRateLimiter()


def get_client_identifier(request: Request) -> str:
    """
    Extract best available client identity for rate limiting:
    1. Authenticated user ID (if available from state)
    2. Forwarded-For header
    3. Direct client host IP
    """
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "user_id"):
        return f"user:{user.user_id}"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    client = getattr(request, "client", None)
    if client and client.host:
        return f"ip:{client.host}"

    return "ip:anonymous"


def enforce_rate_limit(request: Request, endpoint_type: str = "query"):
    """
    FastAPI dependency / check for endpoint rate limiting.
    Raises HTTP 429 when threshold is reached.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    client_id = get_client_identifier(request)

    if endpoint_type == "auth":
        max_req = settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE
    elif endpoint_type == "stream":
        max_req = settings.RATE_LIMIT_STREAM_REQUESTS_PER_MINUTE
    else:
        max_req = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

    key = f"{endpoint_type}:{client_id}"
    allowed, remaining, retry_after = rate_limiter.is_allowed(key, max_req)

    if not allowed:
        logfire.warning(f"🚨 Rate limit exceeded for {key} on {request.url.path} (retry_after={retry_after}s)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                "retry_after_seconds": retry_after
            },
            headers={"Retry-After": str(int(retry_after))}
        )

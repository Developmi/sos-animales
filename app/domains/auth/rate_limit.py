"""Login rate limiting backed by Valkey with in-memory defensive fallback."""

import logging
import time
from datetime import datetime

from app.shared import cache, geo

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60

# In-memory defensive fallback dictionary: IP -> list of attempt timestamps
_login_fallback: dict[str, list[float]] = {}


def _check_memory_rate_limit(ip: str, now: float) -> bool:
    """Evaluate sliding window rate limit using in-memory fallback list."""
    attempts = [t for t in _login_fallback.get(ip, []) if now - t < WINDOW_SECONDS]
    if len(attempts) >= MAX_ATTEMPTS:
        _login_fallback[ip] = attempts
        return False
    attempts.append(now)
    _login_fallback[ip] = attempts

    # Prune stale entries if dictionary exceeds memory budget
    if len(_login_fallback) > 1000:
        stale_ips = [
            k
            for k, timestamps in _login_fallback.items()
            if not any(now - t < WINDOW_SECONDS for t in timestamps)
        ]
        for k in stale_ips:
            del _login_fallback[k]

    return True


async def check_login_rate_limit(ip: str) -> bool:
    """Verify IP rate limit for administrator authentication.

    Uses Valkey INCR with TTL expiration. Falls back to in-memory sliding window
    if Valkey is unavailable, preventing brute-force exposure during cache downtime.
    """
    key = f"ratelimit:login:{ip}:{datetime.now().strftime('%Y%m%d%H%M')}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is None:
            logger.warning(
                "Valkey client not initialized, using memory fallback for login rate limit"
            )
            return _check_memory_rate_limit(ip, now)
        count = await valkey.incr(key)
        if count == 1:
            await valkey.expire(key, WINDOW_SECONDS)
        return count <= MAX_ATTEMPTS
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_login_rate_limit, using memory fallback: %s", e
        )
        return _check_memory_rate_limit(ip, now)

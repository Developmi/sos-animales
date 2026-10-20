import logging
from datetime import datetime
from app.shared import cache, geo

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60


async def check_login_rate_limit(ip: str) -> bool:
    key = f"ratelimit:login:{ip}:{datetime.now().strftime('%Y%m%d%H%M')}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            logger.warning("Valkey not initialized, allowing login rate limit")
            return True
        count = await valkey.incr(key)
        if count == 1:
            await valkey.expire(key, WINDOW_SECONDS)
        return count <= MAX_ATTEMPTS
    except Exception as e:
        logger.warning("Valkey unreachable in check_login_rate_limit: %s", e)
        return True

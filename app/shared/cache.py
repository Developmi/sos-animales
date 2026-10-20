"""Centralized connection and cache management module for Valkey (Redis-compatible).

Decoupled from business logic and geocoding to prevent circular dependencies
across authentication, rate-limiting, and observability components.
"""

import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

valkey_client: Redis | None = None


def init_valkey(url: str) -> Redis:
    """Initialize Valkey client with defensive timeouts and retry policy.

    Must be invoked from the FastAPI lifespan startup handler.
    """
    global valkey_client
    valkey_client = Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        retry_on_timeout=True,
    )
    logger.info("Valkey client initialized with defensive socket timeouts")
    return valkey_client


def get_valkey() -> Redis:
    """Return the initialized Valkey client instance.

    Raises RuntimeError if accessed prior to lifespan initialization.
    """
    if valkey_client is None:
        raise RuntimeError(
            "Valkey client not initialized. Call init_valkey(url) during app startup."
        )
    return valkey_client


async def close_valkey() -> None:
    """Cleanly close the active Valkey connection pool during application shutdown."""
    global valkey_client
    if valkey_client:
        await valkey_client.aclose()
        valkey_client = None
        logger.info("Valkey client closed")

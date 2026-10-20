"""Geocoding utilities via Nominatim/OpenStreetMap.

Converts municipality + address into lat/lng coordinates for Leaflet maps.
Caches results in Valkey to avoid Nominatim rate limiting and respects
fair-use OpenStreetMap policies.
"""

import logging
import httpx
import json
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Valkey client — initialized via init_valkey() during lifespan, not at import-time
valkey_client: Redis | None = None


def init_valkey(url: str) -> Redis:
    """Initialize Valkey client with the provided connection URL.

    Must be called from FastAPI lifespan before any route accesses cache.
    Returns the created Redis instance.
    """
    global valkey_client
    valkey_client = Redis.from_url(url, decode_responses=True)
    logger.info("Valkey client initialized")
    return valkey_client


def get_valkey() -> Redis:
    """Return the initialized Valkey client.

    Raises RuntimeError if the client has not been initialized.
    """
    if valkey_client is None:
        raise RuntimeError(
            "Valkey client not initialized. Call init_valkey(url) during app startup."
        )
    return valkey_client


async def close_valkey() -> None:
    """Close Valkey connection cleanly during application shutdown."""
    global valkey_client
    if valkey_client:
        await valkey_client.aclose()
        valkey_client = None
        logger.info("Valkey client closed")


async def geocode_address(
    address: str, municipality: str
) -> tuple[float | None, float | None]:
    if (
        not address
        or not address.strip()
        or not municipality
        or not municipality.strip()
    ):
        logger.warning(
            "geocode_address called with empty address or municipality — skipping"
        )
        return None, None
    query = f"{address}, {municipality}, Colombia"
    cache_key = f"geo:{query.lower().strip()}"

    # 1. Check Valkey cache
    if valkey_client is not None:
        try:
            cached_result = await valkey_client.get(cache_key)
            if cached_result:
                logger.info(f"⚡ Cache HIT in Valkey for '{query}'")
                lat, lng = json.loads(cached_result)
                return lat, lng
        except Exception as e:
            logger.warning(f"Error reading from Valkey: {e}")
    else:
        logger.warning("Valkey client not initialized, skipping cache for geocode")

    # 2. Query Nominatim if not cached
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "SOSAnimalesColombiaMVP/1.0 (contacto@sos-animales.org)"}
    params = {"q": query, "format": "json", "limit": "1"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                if data:
                    lat = float(data[0]["lat"])
                    lng = float(data[0]["lon"])
                    logger.info(
                        f"📍 Geocoding successful for '{query}': [{lat}, {lng}]"
                    )

                    # 3. Cache in Valkey (TTL 30 days = 2592000 seconds)
                    if valkey_client is not None:
                        try:
                            await valkey_client.set(
                                cache_key, json.dumps([lat, lng]), ex=2592000
                            )
                        except Exception as e:
                            logger.warning(f"Error writing to Valkey: {e}")

                    return lat, lng

            logger.warning(f"⚠️ No coordinates found for address: '{query}'")
            return None, None

    except Exception as e:
        logger.error(f"❌ Error communicating with Nominatim Geocoding API: {e}")
        return None, None

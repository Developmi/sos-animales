"""Shared security and cryptographic utilities.

- generate_pin: generates secure 4-digit numeric PIN (secrets.randbelow).
- hash_pin: hashes PIN with bcrypt (plaintext PIN is never persisted).
- verify_pin: verifies raw PIN against stored bcrypt hash.
- check_rate_limit: verifies IP-based rate limits against Valkey (prevents vote spam).
- check_create_update_rate_limit: limits creation of community reports per IP and target entity.
- mark_as_voted: records a vote in Valkey.
- has_voted_recently: checks if an IP has recently voted without altering state.
- check_pin_rate_limit: limits PIN brute-force attempts per IP and target entity.
- reset_pin_attempts: clears failed PIN attempts after successful verification.
- get_client_ip: resolves real client IP behind reverse proxies (X-Forwarded-For / X-Real-IP).

Reusable across all application domains.
"""

import secrets
import time
from typing import Any
import bcrypt
import logging

from app.shared import cache, geo

logger = logging.getLogger(__name__)

# ponytail: in-memory fallback when Valkey is down, per-account map if throughput matters
_vote_fallback: dict[tuple[str, int], float] = {}
_create_update_fallback: dict[tuple[str, str], float] = {}


def get_client_ip(request: Any) -> str:
    """Resolve real client IP accounting for reverse proxy headers (Caddy/Docker/socat)."""
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        forwarded = headers.get("x-forwarded-for")
        if isinstance(forwarded, str) and forwarded.strip():
            return forwarded.split(",")[0].strip()
        real_ip = headers.get("x-real-ip")
        if isinstance(real_ip, str) and real_ip.strip():
            return real_ip.strip()
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)
    return "127.0.0.1"


def generate_pin() -> str:
    """Generate a 4-digit PIN string (1000 - 9999)."""
    return str(secrets.randbelow(9000) + 1000)


def hash_pin(pin: str) -> str:
    """Return bcrypt hash of the given PIN."""
    # bcrypt operates on bytes; encode plaintext string to utf-8
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)

    # Return hash string for storage in PostgreSQL
    return hashed_bytes.decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify if raw plaintext PIN matches the stored bcrypt hash."""
    # Convert both strings to bytes for bcrypt comparison
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))


async def check_rate_limit(ip: str, update_id: int, window_seconds: int = 900) -> bool:
    """Check if an IP address has already voted for an update within the time window (default: 15 mins).

    Uses Valkey with SET NX (write only if key does not exist) for atomic enforcement.
    Falls back to in-memory dictionary if Valkey is temporarily unreachable.
    Returns True if allowed to vote, False if blocked by rate limit.
    """
    key = f"rate_limit:{ip}:{update_id}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        was_set = await valkey.set(key, "1", ex=window_seconds, nx=True)
        return was_set is True
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_rate_limit, using memory fallback: %s", e
        )
        mem_key = (ip, update_id)
        now = time.time()
        if mem_key in _vote_fallback:
            if now - _vote_fallback[mem_key] < window_seconds:
                return False
        _vote_fallback[mem_key] = now
        # ponytail: prune if dict grows too large during extended outage
        if len(_vote_fallback) > 1000:
            stale = [k for k, v in _vote_fallback.items() if now - v >= window_seconds]
            for k in stale:
                del _vote_fallback[k]
        return True


async def mark_as_voted(ip: str, update_id: int) -> None:
    """Record that an IP has voted (used for report creators to seed their initial vote).

    Uses SET NX to preserve any existing TTL.
    """
    key = f"rate_limit:{ip}:{update_id}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        await valkey.set(key, "1", ex=900, nx=True)
    except Exception as e:
        logger.warning("Valkey unreachable in mark_as_voted: %s", e)
        _vote_fallback[(ip, update_id)] = time.time()


async def has_voted_recently(ip: str, update_id: int) -> bool:
    """Query whether the IP is currently rate-limited (key exists in Valkey).

    Does not accept window_seconds parameter as TTL-based keys cannot deduce
    elapsed time without original EX duration knowledge.
    """
    key = f"rate_limit:{ip}:{update_id}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        return bool(await valkey.exists(key) > 0)
    except Exception as e:
        logger.warning("Valkey unreachable in has_voted_recently: %s", e)
        # Fallback: check in-memory dict
        mem_key = (ip, update_id)
        if mem_key in _vote_fallback:
            return time.time() - _vote_fallback[mem_key] < 900
        return False


_pin_attempts: dict[tuple[str, int], list[float]] = {}


async def check_pin_rate_limit(
    ip: str, animal_id: int, max_attempts: int = 5, window_seconds: int = 3600
) -> bool:
    """Validate that there are no more than max_attempts failed attempts within window."""
    key = f"pin_attempts:{ip}:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is not None:
            attempts = await valkey.get(key)
            if attempts and int(attempts) >= max_attempts:
                return False
            return True
    except Exception as e:
        logger.warning("Valkey error checking pin rate limit: %s", e)

    mem_key = (ip, animal_id)
    history = [t for t in _pin_attempts.get(mem_key, []) if now - t < window_seconds]
    _pin_attempts[mem_key] = history
    return len(history) < max_attempts


async def record_failed_pin_attempt(
    ip: str, animal_id: int, window_seconds: int = 3600
) -> None:
    """Record a failed PIN entry attempt."""
    key = f"pin_attempts:{ip}:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is not None:
            pipe = valkey.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            await pipe.execute()
            return
    except Exception as e:
        logger.warning("Valkey error recording failed pin attempt: %s", e)

    mem_key = (ip, animal_id)
    _pin_attempts.setdefault(mem_key, []).append(now)


async def reset_pin_attempts(ip: str, animal_id: int) -> None:
    """Clear failed PIN entry attempts after a successful PIN verification."""
    key = f"pin_attempts:{ip}:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is not None:
            await valkey.delete(key)
    except Exception as e:
        logger.warning("Valkey error resetting pin attempts: %s", e)

    mem_key = (ip, animal_id)
    _pin_attempts.pop(mem_key, None)


async def check_create_update_rate_limit(
    ip: str,
    campaign_id: int | None = None,
    animal_id: int | None = None,
    window_seconds: int = 900,
) -> bool:
    """Verify if an IP can submit a new community report for a given campaign or animal.

    Uses Valkey SET NX with window_seconds TTL and falls back to _create_update_fallback.
    Returns True if allowed, False if rate-limited.
    """
    target_key = (
        f"campaign:{campaign_id}" if campaign_id is not None else f"animal:{animal_id}"
    )
    key = f"create_update_rate_limit:{ip}:{target_key}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        was_set = await valkey.set(key, "1", ex=window_seconds, nx=True)
        return was_set is True
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_create_update_rate_limit, using memory fallback: %s",
            e,
        )
        mem_key = (ip, target_key)
        now = time.time()
        if mem_key in _create_update_fallback:
            if now - _create_update_fallback[mem_key] < window_seconds:
                return False
        _create_update_fallback[mem_key] = now
        if len(_create_update_fallback) > 1000:
            stale = [
                k
                for k, v in _create_update_fallback.items()
                if now - v >= window_seconds
            ]
            for k in stale:
                del _create_update_fallback[k]
        return True

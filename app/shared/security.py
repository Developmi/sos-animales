"""Shared security and cryptographic utilities.

- generate_pin: generates secure 4-digit numeric PIN (secrets.randbelow).
- hash_pin: hashes PIN with bcrypt (plaintext PIN is never persisted).
- verify_pin: verifies raw PIN against stored bcrypt hash.
- check_rate_limit: verifies anonymized IP/subnet + optional voter token rate limits against Valkey.
- check_create_update_rate_limit: limits creation of community reports per actor and target entity.
- check_action_rate_limit: generic sliding/window rate limiter for public write endpoints.
- mark_as_voted: records a vote in Valkey using anonymized actor digest.
- has_voted_recently: checks if an actor has recently voted without altering state.
- check_pin_rate_limit: limits PIN brute-force attempts per actor AND enforces a global per-entity circuit breaker.
- reset_pin_attempts: clears failed PIN attempts after successful verification.
- get_client_ip: resolves real client IP behind trusted reverse proxies (TRUSTED_PROXY_IPS CIDR).

All Valkey keys and in-memory fallbacks store ONLY irreversible daily-salted HMAC-SHA256 digests
(`anonymize_ip`), never raw plaintext IP addresses (Ley 1581 de 2012 / GDPR Recital 49 compliance).
"""

import logging
import secrets
import time
from typing import Any

import bcrypt

from app.shared import cache, geo
from app.shared.ip_privacy import anonymize_ip, resolve_trusted_client_ip

logger = logging.getLogger(__name__)

# ponytail: in-memory fallback when Valkey is down, keyed by anonymized digest
_vote_fallback: dict[tuple[str, int], float] = {}
_create_update_fallback: dict[tuple[str, str], float] = {}
_action_fallback: dict[tuple[str, str], list[float]] = {}
_pin_attempts: dict[tuple[str, int], list[float]] = {}
_pin_global_attempts: dict[int, list[float]] = {}


def get_client_ip(request: Any) -> str:
    """Resolve real client IP accounting for trusted reverse proxy headers (TRUSTED_PROXY_IPS)."""
    return resolve_trusted_client_ip(request)


def generate_pin() -> str:
    """Generate a 4-digit PIN string (1000 - 9999)."""
    return str(secrets.randbelow(9000) + 1000)


def hash_pin(pin: str) -> str:
    """Return bcrypt hash of the given PIN."""
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify if raw plaintext PIN matches the stored bcrypt hash."""
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))


async def check_rate_limit(
    ip: str,
    update_id: int,
    window_seconds: int = 900,
    voter_token: str | None = None,
) -> bool:
    """Check if an actor (anonymized IP/subnet and optional signed voter cookie) has voted within window.

    Uses Valkey with SET NX for atomic enforcement and falls back to in-memory dictionary.
    Returns True if allowed to vote, False if blocked by either network digest or voter cookie.
    """
    ip_hash = anonymize_ip(ip)
    key = f"rate_limit:{ip_hash}:{update_id}"
    voter_key = f"rate_limit:voter:{voter_token}:{update_id}" if voter_token else None
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        if voter_key is not None and await valkey.exists(voter_key) > 0:
            return False
        was_set = await valkey.set(key, "1", ex=window_seconds, nx=True)
        if was_set is not True:
            return False
        if voter_key is not None:
            await valkey.set(voter_key, "1", ex=window_seconds, nx=True)
        return True
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_rate_limit, using memory fallback: %s", e
        )
        now = time.time()
        mem_key = (ip_hash, update_id)
        voter_mem_key = (f"voter:{voter_token}", update_id) if voter_token else None

        if mem_key in _vote_fallback and now - _vote_fallback[mem_key] < window_seconds:
            return False
        if (
            voter_mem_key is not None
            and voter_mem_key in _vote_fallback
            and now - _vote_fallback[voter_mem_key] < window_seconds
        ):
            return False

        _vote_fallback[mem_key] = now
        if voter_mem_key is not None:
            _vote_fallback[voter_mem_key] = now

        if len(_vote_fallback) > 1000:
            stale = [k for k, v in _vote_fallback.items() if now - v >= window_seconds]
            for k in stale:
                del _vote_fallback[k]
        return True


async def mark_as_voted(
    ip: str, update_id: int, voter_token: str | None = None
) -> None:
    """Record that an actor has voted (used for report creators to seed their initial vote)."""
    ip_hash = anonymize_ip(ip)
    key = f"rate_limit:{ip_hash}:{update_id}"
    voter_key = f"rate_limit:voter:{voter_token}:{update_id}" if voter_token else None
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        await valkey.set(key, "1", ex=900, nx=True)
        if voter_key is not None:
            await valkey.set(voter_key, "1", ex=900, nx=True)
    except Exception as e:
        logger.warning("Valkey unreachable in mark_as_voted: %s", e)
        now = time.time()
        _vote_fallback[(ip_hash, update_id)] = now
        if voter_token is not None:
            _vote_fallback[(f"voter:{voter_token}", update_id)] = now


async def has_voted_recently(
    ip: str, update_id: int, voter_token: str | None = None
) -> bool:
    """Query whether the actor is currently rate-limited (key exists in Valkey or memory fallback)."""
    ip_hash = anonymize_ip(ip)
    key = f"rate_limit:{ip_hash}:{update_id}"
    voter_key = f"rate_limit:voter:{voter_token}:{update_id}" if voter_token else None
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        if await valkey.exists(key) > 0:
            return True
        if voter_key is not None and await valkey.exists(voter_key) > 0:
            return True
        return False
    except Exception as e:
        logger.warning("Valkey unreachable in has_voted_recently: %s", e)
        now = time.time()
        mem_key = (ip_hash, update_id)
        if mem_key in _vote_fallback and now - _vote_fallback[mem_key] < 900:
            return True
        if voter_token is not None:
            v_key = (f"voter:{voter_token}", update_id)
            if v_key in _vote_fallback and now - _vote_fallback[v_key] < 900:
                return True
        return False


async def check_pin_rate_limit(
    ip: str,
    animal_id: int,
    max_attempts: int = 5,
    window_seconds: int = 3600,
    max_global_attempts: int = 15,
) -> bool:
    """Validate per-actor PIN limit AND global per-animal circuit breaker (NIST SP 800-63B)."""
    ip_hash = anonymize_ip(ip)
    key = f"pin_attempts:{ip_hash}:{animal_id}"
    global_key = f"pin_global_attempts:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is not None:
            attempts = await valkey.get(key)
            if attempts and int(attempts) >= max_attempts:
                return False
            global_attempts = await valkey.get(global_key)
            if global_attempts and int(global_attempts) >= max_global_attempts:
                return False
            return True
    except Exception as e:
        logger.warning("Valkey error checking pin rate limit: %s", e)

    mem_key = (ip_hash, animal_id)
    history = [t for t in _pin_attempts.get(mem_key, []) if now - t < window_seconds]
    _pin_attempts[mem_key] = history
    if len(history) >= max_attempts:
        return False

    global_history = [
        t for t in _pin_global_attempts.get(animal_id, []) if now - t < window_seconds
    ]
    _pin_global_attempts[animal_id] = global_history
    return len(global_history) < max_global_attempts


async def record_failed_pin_attempt(
    ip: str, animal_id: int, window_seconds: int = 3600
) -> None:
    """Record a failed PIN entry attempt for both the anonymized actor and the global entity counter."""
    ip_hash = anonymize_ip(ip)
    key = f"pin_attempts:{ip_hash}:{animal_id}"
    global_key = f"pin_global_attempts:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is not None:
            pipe = valkey.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            pipe.incr(global_key)
            pipe.expire(global_key, window_seconds)
            await pipe.execute()
            return
    except Exception as e:
        logger.warning("Valkey error recording failed pin attempt: %s", e)

    mem_key = (ip_hash, animal_id)
    _pin_attempts.setdefault(mem_key, []).append(now)
    _pin_global_attempts.setdefault(animal_id, []).append(now)


async def reset_pin_attempts(ip: str, animal_id: int) -> None:
    """Clear failed PIN entry attempts after a successful PIN verification."""
    ip_hash = anonymize_ip(ip)
    key = f"pin_attempts:{ip_hash}:{animal_id}"
    global_key = f"pin_global_attempts:{animal_id}"
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is not None:
            await valkey.delete(key)
            await valkey.delete(global_key)
    except Exception as e:
        logger.warning("Valkey error resetting pin attempts: %s", e)

    mem_key = (ip_hash, animal_id)
    _pin_attempts.pop(mem_key, None)
    _pin_global_attempts.pop(animal_id, None)


async def check_create_update_rate_limit(
    ip: str,
    campaign_id: int | None = None,
    animal_id: int | None = None,
    window_seconds: int = 900,
    voter_token: str | None = None,
) -> bool:
    """Verify if an actor can submit a new community report for a given campaign or animal."""
    ip_hash = anonymize_ip(ip)
    target_key = (
        f"campaign:{campaign_id}" if campaign_id is not None else f"animal:{animal_id}"
    )
    key = f"create_update_rate_limit:{ip_hash}:{target_key}"
    voter_key = (
        f"create_update_rate_limit:voter:{voter_token}:{target_key}"
        if voter_token
        else None
    )
    valkey = cache.valkey_client or geo.valkey_client
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        if voter_key is not None and await valkey.exists(voter_key) > 0:
            return False
        was_set = await valkey.set(key, "1", ex=window_seconds, nx=True)
        if was_set is not True:
            return False
        if voter_key is not None:
            await valkey.set(voter_key, "1", ex=window_seconds, nx=True)
        return True
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_create_update_rate_limit, using memory fallback: %s",
            e,
        )
        now = time.time()
        mem_key = (ip_hash, target_key)
        voter_mem_key = (f"voter:{voter_token}", target_key) if voter_token else None
        if (
            mem_key in _create_update_fallback
            and now - _create_update_fallback[mem_key] < window_seconds
        ):
            return False
        if (
            voter_mem_key is not None
            and voter_mem_key in _create_update_fallback
            and now - _create_update_fallback[voter_mem_key] < window_seconds
        ):
            return False
        _create_update_fallback[mem_key] = now
        if voter_mem_key is not None:
            _create_update_fallback[voter_mem_key] = now
        if len(_create_update_fallback) > 1000:
            stale = [
                k
                for k, v in _create_update_fallback.items()
                if now - v >= window_seconds
            ]
            for k in stale:
                del _create_update_fallback[k]
        return True


async def check_action_rate_limit(
    ip: str,
    action_scope: str,
    max_attempts: int = 5,
    window_seconds: int = 900,
) -> bool:
    """Generic sliding/counter rate limit for public write endpoints (e.g. animal creation, source registration, freshness)."""
    ip_hash = anonymize_ip(ip)
    key = f"action_rate_limit:{action_scope}:{ip_hash}"
    valkey = cache.valkey_client or geo.valkey_client
    now = time.time()
    try:
        if valkey is None:
            raise RuntimeError("Valkey client not initialized")
        count = await valkey.incr(key)
        if count == 1:
            await valkey.expire(key, window_seconds)
        return int(count) <= max_attempts
    except Exception as e:
        logger.warning(
            "Valkey unreachable in check_action_rate_limit (%s), using memory fallback: %s",
            action_scope,
            e,
        )
        mem_key = (action_scope, ip_hash)
        history = [
            t for t in _action_fallback.get(mem_key, []) if now - t < window_seconds
        ]
        if len(history) >= max_attempts:
            _action_fallback[mem_key] = history
            return False
        history.append(now)
        _action_fallback[mem_key] = history
        if len(_action_fallback) > 1000:
            stale = [
                k
                for k, v in _action_fallback.items()
                if not any(now - t < window_seconds for t in v)
            ]
            for k in stale:
                del _action_fallback[k]
        return True

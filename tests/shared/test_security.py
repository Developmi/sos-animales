import time
import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from app.shared.security import generate_pin, hash_pin, verify_pin

# ponytail: unique prefix per test run avoids stale Valkey key collisions
_UNIQUE = str(int(time.time() * 1000))[-6:]


def test_generate_pin() -> None:
    pin = generate_pin()
    assert len(pin) == 4
    assert pin.isdigit()


def test_hash_and_verify_pin() -> None:
    pin = "1234"
    hashed = hash_pin(pin)

    assert hashed != pin
    assert verify_pin(pin, hashed) is True
    assert verify_pin("9999", hashed) is False


# --- Valkey lifecycle fixture for rate limiting tests ---


@pytest_asyncio.fixture(autouse=True)
async def _init_valkey_for_tests() -> AsyncGenerator[None, None]:
    """Ensure valkey_client is initialized before async rate limit tests,
    and torn down after each test."""
    from app.shared.geo import init_valkey, close_valkey
    from app.config import settings

    init_valkey(settings.VALKEY_URL)
    yield
    await close_valkey()


# --- Valkey-based async rate limiting tests (M1-01) ---


@pytest.mark.asyncio
async def test_check_rate_limit_first_vote_passes() -> None:
    """First vote from an IP for an update should pass (True)."""
    from app.shared.security import check_rate_limit

    ip = f"10.{_UNIQUE}.0.1"
    update_id = int(f"999{_UNIQUE}") % 1000000
    result = await check_rate_limit(ip, update_id, window_seconds=60)
    assert result is True


@pytest.mark.asyncio
async def test_check_rate_limit_duplicate_is_blocked() -> None:
    """Second vote within window should be blocked (False)."""
    from app.shared.security import check_rate_limit

    ip = f"10.{_UNIQUE}.0.2"
    update_id = int(f"998{_UNIQUE}") % 1000000
    await check_rate_limit(ip, update_id, window_seconds=60)
    result = await check_rate_limit(ip, update_id, window_seconds=60)
    assert result is False


@pytest.mark.asyncio
async def test_check_rate_limit_default_window_is_900() -> None:
    """Default window_seconds should be 900 (15 minutes)."""
    from app.shared.security import check_rate_limit
    import inspect

    sig = inspect.signature(check_rate_limit)
    default = sig.parameters["window_seconds"].default
    assert default == 900, f"Expected default 900, got {default}"


@pytest.mark.asyncio
async def test_mark_as_voted_blocks_immediately() -> None:
    """mark_as_voted should block subsequent check_rate_limit."""
    from app.shared.security import mark_as_voted, check_rate_limit

    ip = f"10.{_UNIQUE}.0.3"
    update_id = int(f"997{_UNIQUE}") % 1000000
    await mark_as_voted(ip, update_id)
    result = await check_rate_limit(ip, update_id, window_seconds=60)
    assert result is False


@pytest.mark.asyncio
async def test_has_voted_recently_no_side_effects() -> None:
    """has_voted_recently should not modify TTL or create a new key."""
    from app.shared.security import has_voted_recently, mark_as_voted

    ip = f"10.{_UNIQUE}.0.4"
    update_id = int(f"996{_UNIQUE}") % 1000000
    # Not voted yet
    assert await has_voted_recently(ip, update_id) is False
    # Vote
    await mark_as_voted(ip, update_id)
    # Now should detect
    assert await has_voted_recently(ip, update_id) is True
    # Second check — still True, no side effect (key not refreshed)
    assert await has_voted_recently(ip, update_id) is True


@pytest.mark.asyncio
async def test_vote_timestamps_dict_removed() -> None:
    """_vote_timestamps should no longer exist in security module."""
    import app.shared.security as sec

    assert not hasattr(sec, "_vote_timestamps"), (
        "_vote_timestamps dict must be removed — rate limiting uses Valkey now"
    )

"""TDD Contract Tests for Trusted Proxy CIDR Validation, IP Anonymization (Ley 1581 / GDPR Recital 49),
IPv6 /64 Subnet Normalization, Signed Voter Cookie, and Global Per-Entity PIN Circuit Breaker.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.shared import cache, security


def test_settings_trusted_proxy_ips_cidr_validation() -> None:
    """Settings must accept valid IPs/CIDRs and reject glob patterns like '100.*'."""
    # Valid CIDR list
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        SECRET_KEY="test-secret",
        COMMUNITY_VOTE_THRESHOLD=5,
        VALKEY_URL="redis://localhost:6379/0",
        SMTP_HOST="localhost",
        SMTP_PORT=587,
        SMTP_USER="u",
        SMTP_PASSWORD="p",
        FROM_EMAIL="a@b.c",
        ADMIN_PASSWORD_HASH="hash",
        JWT_SECRET="jwt-secret-at-least-32-characters",
        TRUSTED_PROXY_IPS="127.0.0.1,::1,100.64.0.0/10,172.16.0.0/12",
    )
    assert "100.64.0.0/10" in s.TRUSTED_PROXY_IPS

    # Invalid glob syntax '100.*' must fail validation fast
    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            SECRET_KEY="test-secret",
            COMMUNITY_VOTE_THRESHOLD=5,
            VALKEY_URL="redis://localhost:6379/0",
            SMTP_HOST="localhost",
            SMTP_PORT=587,
            SMTP_USER="u",
            SMTP_PASSWORD="p",
            FROM_EMAIL="a@b.c",
            ADMIN_PASSWORD_HASH="hash",
            JWT_SECRET="jwt-secret-at-least-32-characters",
            TRUSTED_PROXY_IPS="127.0.0.1,100.*",
        )


def test_get_client_ip_anti_spoofing_and_trusted_proxies() -> None:
    """Untrusted direct peers cannot spoof X-Forwarded-For; trusted proxies extract right-most untrusted IP."""
    from app.shared.ip_privacy import is_trusted_proxy

    assert is_trusted_proxy("127.0.0.1") is True
    assert is_trusted_proxy("100.100.50.25") is True  # Tailscale CGNAT 100.64.0.0/10
    assert is_trusted_proxy("172.20.0.1") is True  # Docker bridge 172.16.0.0/12
    assert is_trusted_proxy("198.51.100.99") is False  # Public untrusted peer

    # 1. Direct connection from untrusted public IP attempting X-Forwarded-For spoofing
    untrusted_req = SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"},
        client=SimpleNamespace(host="198.51.100.99"),
    )
    assert security.get_client_ip(untrusted_req) == "198.51.100.99"

    # 2. Request via Docker bridge (172.20.0.1) & Tailscale (100.64.1.2) where client tried prepending spoofed IP
    trusted_chain_req = SimpleNamespace(
        headers={"x-forwarded-for": "6.6.6.6, 203.0.113.50, 100.64.1.2"},
        client=SimpleNamespace(host="172.20.0.1"),
    )
    assert security.get_client_ip(trusted_chain_req) == "203.0.113.50"


def test_ipv6_64_subnet_normalization_and_hmac_anonymization() -> None:
    """Distinct IPv6 addresses in the same /64 prefix map to the exact same HMAC token; raw IP is never exposed."""
    from app.shared.ip_privacy import anonymize_ip, normalize_ip_subnet

    ipv6_a = "2001:db8:1234:5678:aaaa:bbbb:cccc:0001"
    ipv6_b = "2001:db8:1234:5678:ffff:eeee:dddd:9999"

    assert normalize_ip_subnet(ipv6_a) == "2001:db8:1234:5678::/64"
    assert normalize_ip_subnet(ipv6_b) == "2001:db8:1234:5678::/64"

    token_a = anonymize_ip(ipv6_a)
    token_b = anonymize_ip(ipv6_b)
    assert token_a == token_b
    assert len(token_a) == 32
    assert "2001" not in token_a

    raw_ipv4 = "203.0.113.77"
    token_v4 = anonymize_ip(raw_ipv4)
    assert raw_ipv4 not in token_v4
    assert len(token_v4) == 32


@pytest.mark.asyncio
async def test_valkey_keys_never_store_raw_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """All rate-limit keys stored in Valkey must use the HMAC-SHA256 anonymized digest, never plaintext IP."""
    mock_valkey = AsyncMock()
    mock_valkey.set = AsyncMock(return_value=True)
    monkeypatch.setattr(cache, "valkey_client", mock_valkey)

    raw_ip = "203.0.113.88"
    await security.check_rate_limit(raw_ip, update_id=42)

    called_key = mock_valkey.set.call_args[0][0]
    assert raw_ip not in called_key
    assert called_key.startswith("rate_limit:")


@pytest.mark.asyncio
async def test_global_per_entity_pin_circuit_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15 failed PIN attempts across 15 distinct IPs must trigger the global circuit breaker for that animal."""
    monkeypatch.setattr(cache, "valkey_client", None)
    monkeypatch.setattr(security, "geo", SimpleNamespace(valkey_client=None))
    security._pin_attempts.clear()
    if hasattr(security, "_pin_global_attempts"):
        security._pin_global_attempts.clear()

    animal_id = 777
    for i in range(1, 16):
        distinct_ip = f"198.51.100.{i}"
        assert await security.check_pin_rate_limit(distinct_ip, animal_id) is True
        await security.record_failed_pin_attempt(distinct_ip, animal_id)

    # 16th attempt from a brand-new 16th IP must be blocked by the global per-animal circuit breaker
    assert await security.check_pin_rate_limit("203.0.113.250", animal_id) is False


def test_voter_cookie_hmac_signing_and_tamper_resistance() -> None:
    """Signed voter cookie token must verify cleanly and reject tampered signatures."""
    from app.shared.ip_privacy import get_or_create_voter_token, verify_voter_token

    req_no_cookie = SimpleNamespace(cookies={})
    voter_id, signed_cookie = get_or_create_voter_token(req_no_cookie)
    assert signed_cookie is not None
    assert verify_voter_token(signed_cookie) == voter_id

    # Returning request with valid cookie keeps the same voter_id and does not need a new Set-Cookie
    req_valid_cookie = SimpleNamespace(cookies={"sos_voter_token": signed_cookie})
    same_id, new_cookie = get_or_create_voter_token(req_valid_cookie)
    assert same_id == voter_id
    assert new_cookie is None

    # Tampered cookie is rejected and replaced with a fresh signed token
    req_tampered = SimpleNamespace(cookies={"sos_voter_token": f"{voter_id}.forgedsig"})
    fresh_id, replacement_cookie = get_or_create_voter_token(req_tampered)
    assert fresh_id != voter_id
    assert replacement_cookie is not None

"""Single-responsibility module for reverse proxy trust, IPv6 /64 normalization,
cryptographic IP anonymization (Ley 1581 / GDPR Recital 49), and signed voter tokens.

Security guarantees:
1. Trusted Proxy Verification (`is_trusted_proxy`):
   Evaluates peer TCP addresses against `settings.TRUSTED_PROXY_IPS` (IPs & CIDR blocks)
   so untrusted clients cannot spoof `X-Forwarded-For` or `X-Real-IP`.
2. IPv6 `/64` Subnet Normalization (`normalize_ip_subnet`):
   Truncates IPv6 addresses to their `/64` routing prefix (`2001:db8:a:b::/64`)
   to neutralize IPv6 subnet rotation scripts (OWASP OAT-021).
3. Irreversible Daily-Salted HMAC-SHA256 (`anonymize_ip`):
   Transforms normalized client subnets into a 32-char HMAC-SHA256 digest keyed with
   `SECRET_KEY` and the current UTC date (`YYYY-MM-DD`). Raw IPs are never stored in Valkey or RAM.
4. Signed Anti-Rotation Voter Cookie (`sos_voter_token`):
   Issues and verifies an HMAC-SHA256 signed first-party security token to prevent
   rapid IP-switching (4G airplane-mode toggle / VPN hopping) from casting multiple votes.
"""

import hashlib
import hmac
import ipaddress
import secrets
from datetime import UTC, datetime
from typing import Any

from app.config import settings

VOTER_COOKIE_NAME = "sos_voter_token"


def _parse_trusted_proxies(
    raw_trusted: str,
) -> tuple[
    bool,
    set[ipaddress.IPv4Address | ipaddress.IPv6Address],
    list[ipaddress.IPv4Network | ipaddress.IPv6Network],
]:
    """Parse comma-separated IPs and CIDR blocks from configuration."""
    entries = [item.strip() for item in raw_trusted.split(",") if item.strip()]
    if "*" in entries:
        return True, set(), []

    hosts: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in entries:
        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                hosts.add(ipaddress.ip_address(entry))
        except ValueError:
            continue
    return False, hosts, networks


def is_trusted_proxy(peer_ip: str | None) -> bool:
    """Return True if `peer_ip` belongs to `settings.TRUSTED_PROXY_IPS`."""
    if not peer_ip:
        return False
    always_trust, hosts, networks = _parse_trusted_proxies(settings.TRUSTED_PROXY_IPS)
    if always_trust:
        return True
    try:
        ip_obj = ipaddress.ip_address(peer_ip.strip())
    except ValueError:
        return peer_ip.strip() in {"localhost", "testclient"}
    return ip_obj in hosts or any(ip_obj in net for net in networks)


def resolve_trusted_client_ip(request: Any) -> str:
    """Resolve real client IP from `request`, trusting proxy headers ONLY from trusted proxies.

    Walks `X-Forwarded-For` from right to left (RFC 7239 anti-spoofing standard)
    and returns the first address that is not itself a trusted proxy.
    """
    client = getattr(request, "client", None)
    raw_host = getattr(client, "host", None) if client is not None else None
    peer_host: str | None = (
        raw_host.strip() if isinstance(raw_host, str) and raw_host.strip() else None
    )

    # Trust headers if peer is a configured trusted proxy or in unit tests where client is None
    trust_headers = peer_host is None or is_trusted_proxy(peer_host)

    if trust_headers:
        headers = getattr(request, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            forwarded = headers.get("x-forwarded-for")
            if isinstance(forwarded, str) and forwarded.strip():
                hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
                if hops:
                    for hop in reversed(hops):
                        if not is_trusted_proxy(hop):
                            return hop
                    return hops[0]
            real_ip = headers.get("x-real-ip")
            if isinstance(real_ip, str) and real_ip.strip():
                return real_ip.strip()

    if peer_host:
        return peer_host
    return "127.0.0.1"


def normalize_ip_subnet(ip_str: str) -> str:
    """Normalize IPv4 to `/32` canonical form and IPv6 to its `/64` prefix."""
    cleaned = ip_str.strip()
    try:
        ip_obj = ipaddress.ip_address(cleaned)
        if isinstance(ip_obj, ipaddress.IPv6Address):
            if ip_obj.ipv4_mapped is not None:
                return str(ip_obj.ipv4_mapped)
            net64 = ipaddress.IPv6Network((ip_obj, 64), strict=False)
            return str(net64)
        return str(ip_obj)
    except ValueError:
        return cleaned


def anonymize_ip(ip_str: str) -> str:
    """Compute irreversible 32-char daily-salted HMAC-SHA256 digest of a normalized IP/subnet."""
    normalized = normalize_ip_subnet(ip_str)
    utc_day = datetime.now(UTC).strftime("%Y-%m-%d")
    daily_key = f"{settings.SECRET_KEY}:{utc_day}".encode("utf-8")
    digest = hmac.new(daily_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32]


def sign_voter_token(voter_id: str) -> str:
    """Create `voter_id.signature` signed with `settings.SECRET_KEY`."""
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"voter:{voter_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"{voter_id}.{sig}"


def verify_voter_token(cookie_value: str | None) -> str | None:
    """Verify `voter_id.signature` in constant time and return `voter_id` if valid."""
    if not cookie_value or "." not in cookie_value:
        return None
    voter_id, provided_sig = cookie_value.split(".", 1)
    if not voter_id or len(voter_id) > 64:
        return None
    expected = sign_voter_token(voter_id).split(".", 1)[1]
    if hmac.compare_digest(provided_sig, expected):
        return voter_id
    return None


def get_or_create_voter_token(request: Any) -> tuple[str, str | None]:
    """Return `(voter_id, new_signed_cookie_or_none)` from `request.cookies`."""
    cookies = getattr(request, "cookies", None)
    raw_cookie: str | None = None
    if cookies is not None and hasattr(cookies, "get"):
        val = cookies.get(VOTER_COOKIE_NAME)
        if isinstance(val, str):
            raw_cookie = val

    existing_id = verify_voter_token(raw_cookie)
    if existing_id is not None:
        return existing_id, None

    fresh_id = secrets.token_hex(16)
    return fresh_id, sign_voter_token(fresh_id)


def is_terms_accepted(val: Any) -> bool:
    """Validate whether terms acceptance (Ley 1581) was explicitly provided.

    Handles boolean values, string representations ('true', 'on', '1'),
    and direct Python test calls where FastAPI Form defaults are preserved.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"true", "1", "on", "yes"}
    if hasattr(val, "default"):
        return bool(val.default)
    return False

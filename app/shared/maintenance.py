"""Maintenance mode state management.

Provides dual persistence:
1. Primary: Valkey (Redis) key 'sos_animales:maintenance_mode'
2. Fallback: Local sentinel file '/tmp/sos_maintenance.flag'
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.shared import cache

logger = logging.getLogger(__name__)

MAINTENANCE_KEY = "sos_animales:maintenance_mode"
SENTINEL_FILE_PATH = Path("/tmp/sos_maintenance.flag")


async def is_maintenance_active() -> bool:
    """Return True if maintenance mode is currently active via Valkey or file fallback."""
    # 1. Try Valkey first
    try:
        valkey = cache.valkey_client
        if valkey is not None:
            val = await valkey.get(MAINTENANCE_KEY)
            if val is not None:
                # Value could be "1", "0", or serialized JSON
                if isinstance(val, (bytes, bytearray)):
                    val = val.decode("utf-8")
                return str(val).strip() in ("1", "true", "True")
    except Exception as e:
        logger.warning(
            "Valkey check failed for maintenance mode (%s), using file fallback", e
        )

    # 2. Fallback to local sentinel file
    return SENTINEL_FILE_PATH.exists()


async def set_maintenance_mode(active: bool, reason: str = "") -> bool:
    """Enable or disable maintenance mode in Valkey and synchronize sentinel file."""
    now_iso = datetime.now(UTC).isoformat()
    success = False

    # 1. Update Valkey
    try:
        valkey = cache.valkey_client
        if valkey is not None:
            val = "1" if active else "0"
            await valkey.set(MAINTENANCE_KEY, val)
            if active and reason:
                await valkey.set(f"{MAINTENANCE_KEY}:reason", reason)
            success = True
    except Exception as e:
        logger.warning("Valkey set failed for maintenance mode (%s)", e)

    # 2. Synchronize local sentinel file
    try:
        if active:
            SENTINEL_FILE_PATH.write_text(
                json.dumps({"active": True, "reason": reason, "timestamp": now_iso}),
                encoding="utf-8",
            )
        else:
            if SENTINEL_FILE_PATH.exists():
                SENTINEL_FILE_PATH.unlink()
        success = True
    except Exception as e:
        logger.error("Failed to update sentinel file %s: %s", SENTINEL_FILE_PATH, e)

    return success


async def get_maintenance_info() -> dict[str, Any]:
    """Retrieve diagnostic details about the current maintenance mode state."""
    active = False
    source = "default"
    reason = ""

    # Check Valkey
    try:
        valkey = cache.valkey_client
        if valkey is not None:
            val = await valkey.get(MAINTENANCE_KEY)
            if val is not None:
                if isinstance(val, (bytes, bytearray)):
                    val = val.decode("utf-8")
                active = str(val).strip() in ("1", "true", "True")
                source = "valkey"
                raw_reason = await valkey.get(f"{MAINTENANCE_KEY}:reason")
                if raw_reason:
                    if isinstance(raw_reason, (bytes, bytearray)):
                        raw_reason = raw_reason.decode("utf-8")
                    reason = str(raw_reason)
                return {"active": active, "source": source, "reason": reason}
    except Exception:
        pass

    # Check Sentinel file
    if SENTINEL_FILE_PATH.exists():
        try:
            content = json.loads(SENTINEL_FILE_PATH.read_text(encoding="utf-8"))
            return {
                "active": content.get("active", True),
                "source": "file",
                "reason": content.get("reason", ""),
                "timestamp": content.get("timestamp", ""),
            }
        except Exception:
            return {"active": True, "source": "file", "reason": ""}

    return {"active": False, "source": source, "reason": ""}

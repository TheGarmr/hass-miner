"""Pure helper functions for Miner entity data."""
from __future__ import annotations

from typing import Any


def stable_device_id(ip: str | None, mac: str | None) -> str:
    """Return the stable identifier used for HA device/entity IDs."""
    if mac:
        return str(mac).upper()
    if ip:
        return f"ip:{ip}"
    return "unknown"


def resolved_model(miner: Any, data_model: Any) -> str | None:
    """Resolve a display model from pyasic data with miner object fallback."""
    if data_model:
        return str(data_model)

    model = getattr(miner, "model", None)
    if model and not str(model).startswith("Unknown"):
        return str(model)

    raw_model = getattr(miner, "raw_model", None)
    if raw_model:
        return str(raw_model)

    return None


def expected_count(value: int | None, fallback: int) -> int:
    """Use fallback only when a pyasic expected count is unknown."""
    if value is None:
        return fallback
    return value


def device_connections(ip: str | None, mac: str | None) -> set[tuple[str, str]]:
    """Build Home Assistant device connections without adding empty values."""
    connections = set()
    if ip:
        connections.add(("ip", str(ip)))
    if mac:
        connections.add(("mac", str(mac)))
    return connections


def miner_device_info(domain: str, data: dict[str, Any], name: str) -> dict[str, Any]:
    """Build a shared Home Assistant device info payload for miner entities."""
    info = {
        "identifiers": {(domain, data["device_id"])},
        "connections": device_connections(data.get("ip"), data.get("mac")),
        "manufacturer": data.get("make"),
        "model": data.get("model"),
        "sw_version": data.get("fw_ver"),
        "name": name,
    }
    if data.get("ip"):
        info["configuration_url"] = f"http://{data['ip']}"
    return info

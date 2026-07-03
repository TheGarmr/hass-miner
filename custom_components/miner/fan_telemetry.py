"""Fan telemetry helpers shared by the integration and MQTT publishers."""
from __future__ import annotations

from typing import Any

MAX_PLAUSIBLE_FAN_RPM = 15000


async def fetch_rpc_fan_sensors(miner: Any) -> dict[int, dict[str, int]]:
    """Fetch fan speeds directly from the miner RPC stats payload."""
    rpc = getattr(miner, "rpc", None)
    if rpc is None:
        return {}

    try:
        stats = await rpc.stats()
    except Exception:
        return {}

    return extract_rpc_fan_sensors(
        stats,
        expected_fans=getattr(miner, "expected_fans", None),
    )


def extract_rpc_fan_sensors(
    stats: dict[str, Any] | None,
    *,
    expected_fans: int | None = None,
) -> dict[int, dict[str, int]]:
    """Extract compact fan speed sensors from CGMiner-style RPC stats."""
    stats_data = _stats_data(stats)
    if not stats_data:
        return {}

    fan_count = _int(stats_data.get("fan_num")) or expected_fans
    speeds = _plausible_fan_speeds(stats_data)
    fan_count = max(fan_count or 0, len(speeds))
    if fan_count <= 0:
        return {}

    return {
        fan: {"fan_speed": speeds[fan] if fan < len(speeds) else 0}
        for fan in range(fan_count)
    }


def merge_fan_sensors(
    base: dict[int, dict[str, Any]],
    fallback: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Merge fallback fan speeds into base sensors when base values are unusable."""
    merged = {fan: dict(sensors) for fan, sensors in base.items()}
    for fan, sensors in fallback.items():
        target = merged.setdefault(fan, {})
        speed = _int(sensors.get("fan_speed"))
        if speed is None:
            continue
        current = _int(target.get("fan_speed"))
        if current is None or current == 0 or not _plausible_speed(current):
            target["fan_speed"] = speed
    return merged


def _stats_data(stats: dict[str, Any] | None) -> dict[str, Any]:
    """Return the second CGMiner STATS object when present."""
    if not isinstance(stats, dict):
        return {}
    stats_list = stats.get("STATS")
    if not isinstance(stats_list, list) or len(stats_list) < 2:
        return {}
    data = stats_list[1]
    return data if isinstance(data, dict) else {}


def _plausible_fan_speeds(stats_data: dict[str, Any]) -> list[int]:
    """Return non-zero plausible fan speeds ordered by raw fan index."""
    speeds = []
    for index in range(1, 17):
        speed = _int(stats_data.get(f"fan{index}"))
        if speed and _plausible_speed(speed):
            speeds.append(speed)
    return speeds


def _plausible_speed(speed: int) -> bool:
    """Return true for speeds that look like fan RPM values."""
    return 0 <= speed <= MAX_PLAUSIBLE_FAN_RPM


def _int(value: Any) -> int | None:
    """Return value as int when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

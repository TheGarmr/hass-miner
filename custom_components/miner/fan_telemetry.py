"""Fan telemetry helpers shared by the integration and MQTT publishers."""
from __future__ import annotations

from typing import Any


async def fetch_rpc_fan_sensors(miner: Any) -> dict[int, dict[str, Any]]:
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
) -> dict[int, dict[str, Any]]:
    """Extract compact fan speed sensors from CGMiner-style RPC stats."""
    stats_data = _stats_data(stats)
    if not stats_data:
        return {}

    reported_fan_count = _int(stats_data.get("fan_num"))
    fan_count = reported_fan_count or expected_fans
    raw_sensors = _raw_fan_sensors(
        stats_data,
        fan_count=fan_count,
        preserve_zeros=reported_fan_count is not None,
    )
    if raw_sensors:
        return raw_sensors

    fan_count = fan_count or 0
    if fan_count <= 0:
        return {}

    return {
        fan: {"fan_speed": 0}
        for fan in range(fan_count)
    }


def merge_fan_sensors(
    base: dict[int, dict[str, Any]],
    fallback: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Return raw RPC fan sensors when available, otherwise base sensors."""
    if fallback:
        return {fan: dict(sensors) for fan, sensors in fallback.items()}

    merged = {fan: dict(sensors) for fan, sensors in base.items()}
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


def _raw_fan_sensors(
    stats_data: dict[str, Any],
    *,
    fan_count: int | None = None,
    preserve_zeros: bool = False,
) -> dict[int, dict[str, Any]]:
    """Return UI-like fanN speeds compacted to physical fan slots."""
    sensors = {}
    raw_fans: dict[int, int] = {}
    for index in range(1, 17):
        key = f"fan{index}"
        if key not in stats_data:
            continue
        speed = _int(stats_data.get(key))
        if speed is not None and speed >= 0:
            raw_fans[index] = speed

    if not raw_fans:
        return {}

    if fan_count and fan_count > 0 and preserve_zeros:
        selected_fans = _select_fan_window(raw_fans, fan_count)
    else:
        selected_fans = [
            (index, speed)
            for index, speed in sorted(raw_fans.items())
            if speed > 0
        ]
        if fan_count and fan_count > 0:
            selected_fans = selected_fans[:fan_count]

    for slot, (index, speed) in enumerate(selected_fans):
        sensors[slot] = {
            "fan_speed": speed,
            "fan_id": f"fan{index}",
            "fan_index": index,
        }
    return sensors


def _select_fan_window(raw_fans: dict[int, int], fan_count: int) -> list[tuple[int, int]]:
    """Pick the contiguous fanN range that best matches the miner UI."""
    max_index = max(raw_fans)
    last_start = max(1, max_index - fan_count + 1)
    best_start = 1
    best_score: tuple[int, int, int] | None = None

    for start in range(1, last_start + 1):
        speeds = [raw_fans.get(index, 0) for index in range(start, start + fan_count)]
        observed = sum(1 for index in range(start, start + fan_count) if index in raw_fans)
        score = (
            sum(1 for speed in speeds if speed > 0),
            sum(speeds),
            observed,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_start = start

    return [
        (index, raw_fans.get(index, 0))
        for index in range(best_start, best_start + fan_count)
    ]


def _int(value: Any) -> int | None:
    """Return value as int when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

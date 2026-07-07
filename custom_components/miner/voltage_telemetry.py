"""Voltage normalization helpers."""
from __future__ import annotations

from typing import Any

MILLIVOLT_THRESHOLD = 1000


def normalize_voltage(value: Any) -> float | None:
    """Return board voltage in volts.

    Some miner APIs report hashboard voltage in millivolts while pyasic exposes
    the same field without preserving the original unit. Values that are already
    in volts are kept as-is.
    """
    if value is None:
        return None
    try:
        voltage = float(value)
    except (TypeError, ValueError):
        return None

    if abs(voltage) >= MILLIVOLT_THRESHOLD:
        voltage /= 1000
    return round(voltage, 2)

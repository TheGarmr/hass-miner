"""Hashrate telemetry normalization helpers."""
from __future__ import annotations

from typing import Any
from typing import NamedTuple

HASHES_PER_TERA_HASH = 1_000_000_000_000
KILO_SOL_PER_SECOND = "KSol/s"
TERA_HASH_PER_SECOND = "TH/s"

HASH_UNIT_MULTIPLIERS = {
    "H": 1,
    "KH": 1_000,
    "MH": 1_000_000,
    "GH": 1_000_000_000,
    "TH": 1_000_000_000_000,
    "PH": 1_000_000_000_000_000,
    "EH": 1_000_000_000_000_000_000,
    "ZH": 1_000_000_000_000_000_000_000,
}

SOLUTION_UNIT_MULTIPLIERS = {
    "sol": 1,
    "ksol": 1_000,
    "msol": 1_000_000,
    "gsol": 1_000_000_000,
    "tsol": 1_000_000_000_000,
}


class NormalizedHashrate(NamedTuple):
    """A display-ready hashrate value and unit."""

    value: float | None
    unit: str | None


def hashrate_to_th(value: Any) -> float | None:
    """Return hashrate values normalized for legacy callers."""
    return normalize_hashrate(value).value


def normalize_hashrate(value: Any) -> NormalizedHashrate:
    """Return display-ready SHA or Equihash hashrate values."""
    if value is None:
        return NormalizedHashrate(value=None, unit=None)

    rate = getattr(value, "rate", None)
    unit = getattr(value, "unit", None)
    solution_rate = _solution_rate_to_ksol(rate, unit)
    if solution_rate is not None:
        return NormalizedHashrate(value=solution_rate, unit=KILO_SOL_PER_SECOND)

    multiplier = _hash_unit_multiplier(unit)
    if rate is not None and multiplier is not None:
        return NormalizedHashrate(
            value=_rounded(float(rate) * multiplier / HASHES_PER_TERA_HASH),
            unit=TERA_HASH_PER_SECOND,
        )

    try:
        return NormalizedHashrate(value=_rounded(float(value)), unit=None)
    except (TypeError, ValueError):
        return NormalizedHashrate(value=None, unit=None)


def _solution_rate_to_ksol(rate: Any, unit: Any) -> float | None:
    """Return Equihash-style solution rates normalized to KSol/s."""
    if rate is None or unit is None:
        return None

    unit_text = str(unit).lower()
    if "sol" not in unit_text:
        return None

    solution_unit = unit_text.removesuffix("/s")
    multiplier = SOLUTION_UNIT_MULTIPLIERS.get(solution_unit)
    if multiplier is None:
        return None

    ksol = float(rate) * multiplier / 1_000
    # pyasic old Antminer Equihash classes currently report chain_rate values
    # inflated by 1e6 while labeling them KSol/s.
    if ksol >= 1_000_000:
        ksol /= 1_000_000
    return _rounded(ksol)


def _hash_unit_multiplier(unit: Any) -> int | None:
    """Return a multiplier to H/s for SHA-style hashrate units."""
    if unit is None:
        return None

    unit_text = str(unit).lower()
    if "sol" in unit_text:
        return None

    unit_name = getattr(unit, "name", None)
    if isinstance(unit_name, str) and unit_name in HASH_UNIT_MULTIPLIERS:
        return HASH_UNIT_MULTIPLIERS[unit_name]

    if unit_text.endswith("h/s"):
        return _int(getattr(unit, "value", None))

    return None


def _rounded(value: float) -> float:
    """Round display hashrate values consistently."""
    return round(value, 2)


def _int(value: Any) -> int | None:
    """Return value as int when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

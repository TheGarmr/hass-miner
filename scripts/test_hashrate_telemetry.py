"""Lightweight tests for hashrate telemetry normalization."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    """Load hashrate_telemetry without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "hashrate_telemetry.py"
    spec = importlib.util.spec_from_file_location("miner_hashrate_telemetry", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Unit:
    """Minimal unit object with pyasic-like name and value."""

    def __init__(self, name: str, value: int, label: str) -> None:
        """Store unit metadata."""
        self.name = name
        self.value = value
        self._label = label

    def __str__(self) -> str:
        """Return the display unit."""
        return self._label


class Hashrate:
    """Minimal pyasic-like hashrate object."""

    def __init__(self, rate: float, unit: Unit) -> None:
        """Store rate and unit."""
        self.rate = rate
        self.unit = unit

    def __float__(self) -> float:
        """Return raw rate like pyasic hashrate objects do."""
        return float(self.rate)


def main():
    """Run hashrate normalization assertions."""
    hashrate = load_module()

    assert hashrate.normalize_hashrate(
        Hashrate(425_106_940_000_000, Unit("H", 1, "H/s"))
    ) == hashrate.NormalizedHashrate(425.11, "TH/s")
    assert hashrate.normalize_hashrate(
        Hashrate(425_106.94, Unit("GH", 1_000_000_000, "GH/s"))
    ) == hashrate.NormalizedHashrate(425.11, "TH/s")
    assert hashrate.normalize_hashrate(
        Hashrate(425.10694, Unit("TH", 1_000_000_000_000, "TH/s"))
    ) == hashrate.NormalizedHashrate(425.11, "TH/s")
    assert hashrate.normalize_hashrate(
        Hashrate(141_870_000, Unit("KH", 1_000, "KSol/s"))
    ) == hashrate.NormalizedHashrate(141.87, "KSol/s")
    assert hashrate.normalize_hashrate(
        Hashrate(463_970_000, Unit("KH", 1_000, "KSol/s"))
    ) == hashrate.NormalizedHashrate(463.97, "KSol/s")
    assert hashrate.hashrate_with_vnish_fallback(
        Hashrate(0, Unit("H", 1, "H/s")),
        {"instant_hashrate": 425.1, "average_hashrate": 424.9},
        is_mining=True,
    ) == hashrate.NormalizedHashrate(425.1, "TH/s")
    assert hashrate.hashrate_with_vnish_fallback(
        None,
        {"instant_hashrate": 0, "average_hashrate": 424.9},
        is_mining=True,
    ) == hashrate.NormalizedHashrate(424.9, "TH/s")
    assert hashrate.hashrate_with_vnish_fallback(
        None,
        {"instant_hashrate": 0, "average_hashrate": 424.9},
        is_mining=False,
    ) == hashrate.NormalizedHashrate(None, None)
    assert hashrate.ideal_hashrate_with_vnish_fallback(
        None,
        {"nominal_hashrate": 424.19, "stock_hashrate": 401.17},
    ) == hashrate.NormalizedHashrate(424.19, "TH/s")
    assert hashrate.normalize_hashrate(None) == hashrate.NormalizedHashrate(None, None)


if __name__ == "__main__":
    main()

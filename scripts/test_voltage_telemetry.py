"""Lightweight tests for voltage normalization."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    """Load voltage_telemetry without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "voltage_telemetry.py"
    spec = importlib.util.spec_from_file_location("miner_voltage_telemetry", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    """Run voltage normalization assertions."""
    voltage = load_module()

    assert voltage.normalize_voltage(None) is None
    assert voltage.normalize_voltage("bad") is None
    assert voltage.normalize_voltage(12.1) == 12.1
    assert voltage.normalize_voltage("21.08") == 21.08
    assert voltage.normalize_voltage(12000) == 12.0
    assert voltage.normalize_voltage(21080) == 21.08
    assert voltage.normalize_voltage(21585) == 21.59


if __name__ == "__main__":
    main()

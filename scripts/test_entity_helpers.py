"""Lightweight tests for miner entity helper functions."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    """Load entity_helpers without importing Home Assistant package modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "entity_helpers.py"
    spec = importlib.util.spec_from_file_location("miner_entity_helpers", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeMiner:
    """Fake miner exposing model fallback fields."""

    model = "Antminer Z11"
    raw_model = "Z11"


class UnknownVnishMiner:
    """Fake miner exposing a pyasic partial support model name."""

    model = "Unknown (VNish)"
    raw_model = None


def main():
    """Run helper assertions."""
    helpers = load_module()

    assert helpers.stable_device_id("192.0.2.10", "aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert helpers.stable_device_id("192.0.2.10", None) == "ip:192.0.2.10"
    assert helpers.stable_device_id(None, None) == "unknown"

    assert helpers.resolved_model(FakeMiner(), "Z15") == "Z15"
    assert helpers.resolved_model(FakeMiner(), None) == "Antminer Z11"
    assert helpers.resolved_model(UnknownVnishMiner(), None) is None
    assert helpers.resolved_model(object(), None) is None

    assert helpers.expected_count(None, 4) == 4
    assert helpers.expected_count(0, 4) == 0
    assert helpers.expected_count(3, 4) == 3

    assert helpers.device_connections("192.0.2.10", "aa:bb") == {
        ("ip", "192.0.2.10"),
        ("mac", "aa:bb"),
    }
    assert helpers.device_connections(None, None) == set()

    device_info = helpers.miner_device_info(
        "miner",
        {
            "device_id": "AA:BB",
            "ip": "192.0.2.10",
            "mac": "AA:BB",
            "make": "Antminer",
            "model": "S21+ Hydro",
            "fw_ver": "Vnish 1.2.8",
        },
        "S21",
    )
    assert device_info["identifiers"] == {("miner", "AA:BB")}
    assert device_info["configuration_url"] == "http://192.0.2.10"
    assert device_info["manufacturer"] == "Antminer"
    assert device_info["model"] == "S21+ Hydro"


if __name__ == "__main__":
    main()

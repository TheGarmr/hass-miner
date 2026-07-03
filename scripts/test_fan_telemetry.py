"""Lightweight tests for fan telemetry normalization."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    """Load fan_telemetry without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "fan_telemetry.py"
    spec = importlib.util.spec_from_file_location("miner_fan_telemetry", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    """Run fan telemetry assertions."""
    fan_telemetry = load_module()

    z11_stats = {
        "STATS": [
            {},
            {
                "fan_num": 2,
                "fan1": 4920,
                "fan2": 4800,
                "fan3": 0,
                "fan4": 0,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(z11_stats) == {
        0: {"fan_speed": 4920},
        1: {"fan_speed": 4800},
    }

    z15_stats = {
        "STATS": [
            {},
            {
                "fan_num": 2,
                "fan1": 0,
                "fan2": 5040,
                "fan3": 25920,
                "fan4": 0,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(z15_stats) == {
        0: {"fan_speed": 5040},
        1: {"fan_speed": 0},
    }

    merged = fan_telemetry.merge_fan_sensors(
        {
            0: {"fan_speed": 25920, "fan_status": "ok"},
            1: {"fan_speed": 0},
        },
        {
            0: {"fan_speed": 5040},
            1: {"fan_speed": 0},
        },
    )
    assert merged == {
        0: {"fan_speed": 5040, "fan_status": "ok"},
        1: {"fan_speed": 0},
    }


if __name__ == "__main__":
    main()

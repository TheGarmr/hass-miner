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
        0: {"fan_speed": 4920, "fan_id": "fan1", "fan_index": 1},
        1: {"fan_speed": 4800, "fan_id": "fan2", "fan_index": 2},
    }

    z15_stats = {
        "STATS": [
            {},
            {
                "fan_num": 2,
                "fan1": 0,
                "fan2": 5040,
                "fan3": 30600,
                "fan4": 0,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(z15_stats) == {
        0: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
        1: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
    }

    z15_failed_first_fan_stats = {
        "STATS": [
            {},
            {
                "fan_num": 2,
                "fan1": 0,
                "fan2": 0,
                "fan3": 4560,
                "fan4": 0,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(z15_failed_first_fan_stats) == {
        0: {"fan_speed": 0, "fan_id": "fan2", "fan_index": 2},
        1: {"fan_speed": 4560, "fan_id": "fan3", "fan_index": 3},
    }

    stats_without_reported_fan_count = {
        "STATS": [
            {},
            {
                "fan1": 5040,
                "fan2": 0,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(
        stats_without_reported_fan_count,
        expected_fans=4,
    ) == {
        0: {"fan_speed": 5040, "fan_id": "fan1", "fan_index": 1},
    }

    z15_pro_stats = {
        "STATS": [
            {},
            {
                "fan_num": 1,
                "fan1": 7100,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(z15_pro_stats) == {
        0: {"fan_speed": 7100, "fan_id": "fan1", "fan_index": 1},
    }

    merged = fan_telemetry.merge_fan_sensors(
        {
            0: {"fan_speed": 30600, "fan_status": "ok"},
            1: {"fan_speed": 0},
        },
        {
            0: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
            1: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
        },
    )
    assert merged == {
        0: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
        1: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
    }


if __name__ == "__main__":
    main()

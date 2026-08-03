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
        1: {"fan_speed": 4920, "fan_id": "fan1", "fan_index": 1},
        2: {"fan_speed": 4800, "fan_id": "fan2", "fan_index": 2},
    }

    zero_based_stats = {
        "STATS": [
            {},
            {
                "fan_num": 2,
                "fan0": 4920,
                "fan1": 4800,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(zero_based_stats) == {
        0: {"fan_speed": 4920, "fan_id": "fan0", "fan_index": 0},
        1: {"fan_speed": 4800, "fan_id": "fan1", "fan_index": 1},
    }

    s19_stats_with_extra_fan0 = {
        "STATS": [
            {},
            {
                "fan_num": 4,
                "fan0": 6000,
                "fan1": 5910,
                "fan2": 6000,
                "fan3": 5610,
                "fan4": 5610,
            },
        ]
    }
    assert fan_telemetry.extract_rpc_fan_sensors(s19_stats_with_extra_fan0) == {
        1: {"fan_speed": 5910, "fan_id": "fan1", "fan_index": 1},
        2: {"fan_speed": 6000, "fan_id": "fan2", "fan_index": 2},
        3: {"fan_speed": 5610, "fan_id": "fan3", "fan_index": 3},
        4: {"fan_speed": 5610, "fan_id": "fan4", "fan_index": 4},
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
        2: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
        3: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
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
        2: {"fan_speed": 0, "fan_id": "fan2", "fan_index": 2},
        3: {"fan_speed": 4560, "fan_id": "fan3", "fan_index": 3},
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
        1: {"fan_speed": 5040, "fan_id": "fan1", "fan_index": 1},
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
        1: {"fan_speed": 7100, "fan_id": "fan1", "fan_index": 1},
    }

    merged = fan_telemetry.merge_fan_sensors(
        {
            0: {"fan_speed": 30600, "fan_status": "ok"},
            1: {"fan_speed": 0},
        },
        {
            2: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
            3: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
        },
    )
    assert merged == {
        2: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
        3: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
    }

    s19_merged = fan_telemetry.merge_fan_sensors(
        {},
        {
            1: {"fan_speed": 5910, "fan_id": "fan1", "fan_index": 1},
            2: {"fan_speed": 6000, "fan_id": "fan2", "fan_index": 2},
            3: {"fan_speed": 5610, "fan_id": "fan3", "fan_index": 3},
            4: {"fan_speed": 5610, "fan_id": "fan4", "fan_index": 4},
        },
        {
            0: {"fan_speed": 6000, "fan_status": "ok", "fan_max_speed": 6500},
            1: {"fan_speed": 6000, "fan_status": "ok", "fan_max_speed": 6500},
            2: {"fan_speed": 5610, "fan_status": "ok", "fan_max_speed": 6500},
            3: {"fan_speed": 5610, "fan_status": "ok", "fan_max_speed": 6500},
        },
    )
    assert sorted(s19_merged) == [1, 2, 3, 4]
    assert s19_merged[1] == {
        "fan_speed": 5910,
        "fan_id": "fan1",
        "fan_index": 1,
        "fan_status": "ok",
        "fan_max_speed": 6500,
    }
    assert s19_merged[4]["fan_status"] == "ok"
    assert all(
        fan_data["fan_max_speed"] == 6500
        for fan_data in s19_merged.values()
    )

    z15_merged = fan_telemetry.merge_fan_sensors(
        {},
        {
            2: {"fan_speed": 5040, "fan_id": "fan2", "fan_index": 2},
            3: {"fan_speed": 30600, "fan_id": "fan3", "fan_index": 3},
        },
        {
            0: {"fan_status": "ok"},
            1: {"fan_status": "ok"},
        },
    )
    assert sorted(z15_merged) == [2, 3]
    assert z15_merged[2]["fan_status"] == "ok"
    assert z15_merged[3]["fan_status"] == "ok"


if __name__ == "__main__":
    main()

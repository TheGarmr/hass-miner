"""Lightweight tests for VNish telemetry normalization."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


def load_module():
    """Load vnish_telemetry without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    custom_components_path = root / "custom_components"
    miner_path = custom_components_path / "miner"
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
    miner_package = sys.modules.setdefault(
        "custom_components.miner",
        types.ModuleType("custom_components.miner"),
    )
    miner_package.__path__ = [str(miner_path)]
    module_path = root / "custom_components" / "miner" / "vnish_telemetry.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.miner.vnish_telemetry",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    """Run VNish telemetry assertions."""
    vnish = load_module()

    summary = {
        "miner": {
            "miner_type": "Antminer S21+ Hydro (Vnish 1.2.8)",
            "average_hashrate": 421.68,
            "instant_hashrate": 420.23,
            "hr_nominal": 424189.44,
            "hr_stock": 401166.0,
            "pcb_temp": {"min": 28, "max": 51},
            "chip_temp": {"min": 28, "max": 51},
            "power_efficiency": 14.52,
            "hw_errors": 82,
            "hw_errors_percent": 0.0,
            "devfee_percent": 2.66,
            "miner_status": {
                "miner_state": "mining",
                "miner_state_time": 14334,
            },
            "cooling": {
                "fan_num": 1,
                "fans": [
                    {"id": 0, "rpm": 0, "status": "ok", "max_rpm": 6500},
                ],
                "settings": {"mode": {"name": "immersion"}},
                "fan_duty": 100,
            },
            "chains": [
                {
                    "id": 1,
                    "frequency": 727.12,
                    "voltage": 21585,
                    "power_consumption": 2033,
                    "hashrate_ideal": 140915.05,
                    "hashrate_rt": 138615.55,
                    "hashrate_percentage": 99.2,
                    "hr_error": 0.0,
                    "hw_errors": 67,
                    "pcb_temp": {"min": 29, "max": 49},
                    "chip_temp": {"min": 29, "max": 49},
                    "chip_statuses": {"red": 0, "orange": 1, "grey": 94},
                    "inlet_water_temp": 29,
                    "outlet_water_temp": 39,
                }
            ],
        }
    }
    chips = {
        "chips_per_chain": 95,
        "chains": [
            {
                "id": 1,
                "chips": [
                    {"id": 1, "status": "grey", "errors": 2},
                    {"id": 2, "status": "orange", "errors": 1},
                ],
            }
        ],
    }
    perf_summary = {
        "current_preset": {"name": "6619", "pretty": "6619 watt ~ 422 TH"}
    }
    settings = {
        "miner": {
            "cooling": {
                "mode": {"name": "immers"},
                "fan_min_duty": 10,
                "fan_max_duty": 100,
                "min_startup_water_temp": 20,
            }
        }
    }
    info = {
        "miner": "Antminer S21+ Hydro",
        "fw_name": "Vnish",
        "fw_version": "1.2.8",
        "system": {
            "network_status": {
                "mac": "02:B8:50:0D:4D:49",
                "hostname": "Antminer",
            }
        },
    }

    data = vnish.normalize_vnish_extended_data(
        summary=summary,
        chips=chips,
        perf_summary=perf_summary,
        info=info,
        settings=settings,
    )

    assert data["device"]["make"] == "Antminer"
    assert data["device"]["model"] == "Antminer S21+ Hydro"
    assert data["device"]["fw_ver"] == "Vnish 1.2.8"
    assert data["device"]["mac"] == "02:B8:50:0D:4D:49"

    miner_sensors = data["miner_sensors"]
    assert miner_sensors["temperature"] == 51
    assert miner_sensors["average_hashrate"] == 421.68
    assert miner_sensors["nominal_hashrate"] == 424.19
    assert miner_sensors["stock_hashrate"] == 401.17
    assert miner_sensors["mining_time"] == 14334
    assert miner_sensors["water_inlet_temperature_min"] == 29
    assert miner_sensors["water_outlet_temperature_max"] == 39
    assert miner_sensors["current_preset"] == "6619 watt ~ 422 TH"
    assert miner_sensors["cooling_mode"] == "immersion"
    assert miner_sensors["fan_duty"] == 100
    assert miner_sensors["cooling_min_fan_duty"] == 10
    assert miner_sensors["cooling_max_fan_duty"] == 100
    assert miner_sensors["minimum_startup_water_temperature"] == 20
    assert miner_sensors["total_chips"] == 2
    assert miner_sensors["bad_chips"] == 1
    assert miner_sensors["chip_errors"] == 3

    board = data["board_sensors"][0]
    assert board["board_hashrate"] == 138.62
    assert board["board_hashrate_ideal"] == 140.92
    assert board["board_power"] == 2033
    assert board["board_voltage"] == 21.59
    assert board["chip_status_orange"] == 1
    assert board["inlet_water_temperature"] == 29
    assert board["outlet_water_temperature"] == 39
    assert board["water_temperature_delta"] == 10

    fan = data["fan_sensors"][0]
    assert fan["fan_speed"] == 0
    assert fan["fan_status"] == "ok"
    assert fan["fan_max_speed"] == 6500

    assert data["sensor_attributes"] == {}
    assert data["cooling"] == {"mode": "immersion", "fan_count": 1}


if __name__ == "__main__":
    main()

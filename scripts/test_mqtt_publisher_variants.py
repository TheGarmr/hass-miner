"""Tests for copied miner MQTT publisher variants."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path


def load_publisher_module(filename: str):
    """Load a publisher script as a module."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMiner:
    """Minimal miner object for normalization tests."""

    model = "Antminer"


class FakeAsyncMiner:
    """Minimal async miner object for collect_telemetry tests."""

    model = "S21+ Hydro"

    def __init__(self) -> None:
        """Initialize captured call state."""
        self.web = None
        self.exclude = None

    async def get_data(self, *, exclude=None):
        """Return fake telemetry and capture excluded data options."""
        self.exclude = exclude
        return FakeData("S21+ Hydro")


class FakeData:
    """Minimal pyasic-like data object for normalization tests."""

    def __init__(self, model: str) -> None:
        """Store the model name to expose through model_dump."""
        self._model = model

    def model_dump(self, *, mode):
        """Return pyasic-like telemetry data."""
        assert mode == "json"
        return {
            "make": "Antminer",
            "model": self._model,
            "fw_ver": f"{self._model}-fw",
            "mac": "AA:BB:CC:DD:EE:FF",
            "is_mining": True,
            "uptime": 123,
            "hashrate": {"rate": 135000, "unit": "H/s"},
            "hashboards": [{"slot": 0, "chips": 3}],
            "fans": [{"speed": 6000}],
            "env_temp": 25.5,
            "temperature_avg": 63,
            "wattage": 1400,
            "voltage": 12.1,
            "wattage_limit": 1500,
        }


class FakeGenericFirmwareData(FakeData):
    """pyasic-like data that only reports the firmware family."""

    def model_dump(self, *, mode):
        """Return telemetry with generic VNish firmware."""
        data = super().model_dump(mode=mode)
        data["fw_ver"] = "VNish"
        return data


def assert_parser_defaults(module, expected_topic: str) -> None:
    """Assert copied scripts keep the requested service defaults."""
    args = module.parse_args(["192.0.2.10"])

    assert args.ip == "192.0.2.10"
    assert args.mqtt_host == module.MQTT_HOST
    assert args.mqtt_port == module.MQTT_PORT
    assert args.topic == expected_topic
    assert args.interval == module.DEFAULT_INTERVAL
    assert args.web_username == module.MINER_WEB_USERNAME
    assert args.web_password == module.MINER_WEB_PASSWORD


def assert_normalized_payload(module, expected_model: str) -> None:
    """Assert telemetry payloads remain JSON-safe for copied scripts."""
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)

    payload = module.normalize_telemetry(
        "192.0.2.10", FakeMiner(), FakeData(expected_model), now=now
    )

    assert payload["ip"] == "192.0.2.10"
    assert payload["class"] == "FakeMiner"
    assert payload["make"] == "Antminer"
    assert payload["model"] == expected_model
    assert payload["firmware"] == f"{expected_model}-fw"
    assert payload["hashrate"] == {"rate": 135000, "unit": "H/s"}
    assert payload["temperature"] == {"env": 25.5, "average": 63}
    assert payload["power"] == {"wattage": 1400, "voltage": 12.1, "wattage_limit": 1500}
    assert payload["device"] == {}
    assert payload["miner_sensors"] == {}
    assert payload["board_sensors"] == {}
    assert payload["fan_sensors"] == {}
    assert payload["sensor_attributes"] == {}
    assert payload["timestamp"] == "2026-07-03T12:00:00+00:00"

    json.dumps(payload)


def assert_extended_payload(module) -> None:
    """Assert integration-style extended telemetry is published."""
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    extended = {
        "device": {
            "make": "Antminer",
            "model": "Antminer S21+ Hydro",
            "fw_ver": "Vnish 1.2.8",
            "mac": "02:B8:50:0D:4D:49",
        },
        "miner_sensors": {
            "average_hashrate": 421.68,
            "cooling_mode": "immersion",
            "fan_duty": 100,
            "water_inlet_temperature_min": 29,
            "water_outlet_temperature_max": 39,
        },
        "board_sensors": {
            0: {
                "board_hashrate": 138.62,
                "board_power": 2033,
                "board_temperature": 49,
                "inlet_water_temperature": 29,
                "outlet_water_temperature": 39,
            }
        },
        "fan_sensors": {0: {"fan_speed": 0, "fan_status": "ok"}},
        "sensor_attributes": {},
    }

    payload = module.normalize_telemetry(
        "192.0.2.10",
        FakeMiner(),
        FakeData("Unknown (VNish)"),
        now=now,
        extended=extended,
    )

    assert payload["model"] == "Antminer S21+ Hydro"
    assert payload["firmware"] == "Unknown (VNish)-fw"
    assert payload["mac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["device"]["fw_ver"] == "Vnish 1.2.8"
    assert payload["miner_sensors"]["average_hashrate"] == 421.68
    assert payload["miner_sensors"]["cooling_mode"] == "immersion"
    assert payload["miner_sensors"]["fan_duty"] == 100
    assert payload["board_sensors"]["0"]["inlet_water_temperature"] == 29
    assert payload["board_sensors"]["0"]["board_power"] == 2033
    assert payload["fan_sensors"]["0"]["fan_status"] == "ok"
    assert payload["sensor_attributes"] == {}

    json.dumps(payload)


def assert_generic_firmware_payload(module) -> None:
    """Assert full VNish firmware version replaces generic firmware family."""
    extended = {"device": {"fw_ver": "Vnish 1.2.8"}}

    payload = module.normalize_telemetry(
        "192.0.2.10",
        FakeMiner(),
        FakeGenericFirmwareData("S21+ Hydro"),
        extended=extended,
    )

    assert payload["firmware"] == "Vnish 1.2.8"


def assert_corrected_fan_payload(module) -> None:
    """Assert corrected RPC fan speeds are published."""
    payload = module.normalize_telemetry(
        "192.0.2.10",
        FakeMiner(),
        FakeData("Z15"),
        fan_sensors={
            0: {"fan_speed": 5040},
            1: {"fan_speed": 0},
        },
    )

    assert payload["fan_sensors"] == {
        "0": {"fan_speed": 5040},
        "1": {"fan_speed": 0},
    }
    assert payload["fans"] == [{"speed": 5040}, {"speed": 0}]


def test_z15_defaults_and_payload():
    """Z15 copy should expose the Z15 MQTT topic and JSON payload."""
    module = load_publisher_module("z15_mqtt_publisher.py")

    assert_parser_defaults(module, "miner/z15")
    assert_normalized_payload(module, "Z15")
    assert_extended_payload(module)
    assert_generic_firmware_payload(module)
    assert_corrected_fan_payload(module)


def test_s21_plus_hydro_defaults_and_payload():
    """S21+ Hydro copy should expose the S21+ Hydro MQTT topic and JSON payload."""
    module = load_publisher_module("s21_plus_hydro_mqtt_publisher.py")

    assert_parser_defaults(module, "miner/s21_plus_hydro")
    assert_normalized_payload(module, "S21+ Hydro")
    assert_extended_payload(module)
    assert_generic_firmware_payload(module)
    assert_corrected_fan_payload(module)


def test_s21_plus_hydro_collect_telemetry_skips_config():
    """S21+ Hydro should skip pyasic VNish config collection."""
    module = load_publisher_module("s21_plus_hydro_mqtt_publisher.py")
    miner = FakeAsyncMiner()
    original_get_miner = module.pyasic.get_miner
    original_fetch_extended = module.fetch_extended_telemetry

    async def fake_get_miner(ip):
        assert ip == "192.0.2.10"
        return miner

    async def fake_fetch_extended(found_miner):
        assert found_miner is miner
        return {"miner_sensors": {"average_hashrate": 421.68}}

    module.pyasic.get_miner = fake_get_miner
    module.fetch_extended_telemetry = fake_fetch_extended
    try:
        args = module.parse_args(["192.0.2.10"])
        payload = asyncio.run(module.collect_telemetry(args))
    finally:
        module.pyasic.get_miner = original_get_miner
        module.fetch_extended_telemetry = original_fetch_extended

    assert module.DataOptions.CONFIG in miner.exclude
    assert payload["model"] == "S21+ Hydro"
    assert payload["miner_sensors"]["average_hashrate"] == 421.68


if __name__ == "__main__":
    test_z15_defaults_and_payload()
    test_s21_plus_hydro_defaults_and_payload()
    test_s21_plus_hydro_collect_telemetry_skips_config()

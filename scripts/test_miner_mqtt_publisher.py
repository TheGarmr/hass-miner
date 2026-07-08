"""Tests for the unified miner MQTT publisher."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def load_publisher_module():
    """Load the unified publisher script as a module."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "miner_mqtt_publisher.py"
    spec = importlib.util.spec_from_file_location("miner_mqtt_publisher", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeMiner:
    """Minimal miner object for config resolution tests."""

    def __init__(self, model: str) -> None:
        """Store model metadata."""
        self.model = model
        self.raw_model = model
        self.web = FakeWeb()
        self.exclude = None

    async def get_data(self, *, exclude=None):
        """Return fake telemetry and capture excluded options."""
        self.exclude = exclude
        return FakeData(self.model)


class VNish(FakeMiner):
    """Fake miner with a generic pyasic VNish class name."""


class FakeWeb:
    """Minimal web object for credential assertions."""

    username = None
    pwd = None


class VNishWebAPI(FakeWeb):
    """Fake VNish web object for unknown miner detection."""


class FakeData:
    """Minimal pyasic-like data object for normalization tests."""

    def __init__(self, model: str) -> None:
        """Store model name to expose through model_dump."""
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


class FakePublishResult:
    """Fake paho publish result."""

    rc = 0


class FakeMqttClient:
    """Capture MQTT publish calls."""

    def __init__(self) -> None:
        """Initialize captured messages."""
        self.messages = []

    def publish(self, topic, payload, *, retain):
        """Capture one publish call."""
        self.messages.append((topic, payload, retain))
        return FakePublishResult()


def test_model_settings_and_file_names():
    """Detected models should map to configured topics and payload files."""
    module = load_publisher_module()

    assert module.resolve_runtime_config(FakeMiner("Z11")).topic == "miner/z11"
    assert module.resolve_runtime_config(FakeMiner("Z15 (Stock)")).topic == "miner/z15"
    s21_config = module.resolve_runtime_config(FakeMiner("S21+ Hydro"))
    assert s21_config.topic == "miner/s21_plus_hydro"
    assert s21_config.web_username == "admin"
    assert s21_config.web_password == "admin"
    assert s21_config.exclude_config is True

    module.PAYLOAD_FILE_PREFIX = "payload_"
    assert str(module.payload_file_path({"miner_model": "Z11"})) == "payload_z11.json"
    assert (
        str(module.payload_file_path({"miner_model": "S21+ Hydro"}))
        == "payload_s21_plus_hydro.json"
    )


def test_normalized_payload_is_json_safe():
    """Unified publisher should produce the same stable payload shape."""
    module = load_publisher_module()
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)

    payload = module.normalize_telemetry(
        "192.0.2.10",
        FakeMiner("Z15"),
        FakeData("Z15"),
        now=now,
        fan_sensors={0: {"fan_speed": 5040}, 1: {"fan_speed": 0}},
        extended={
            "miner_sensors": {
                "average_hashrate": 463.97,
                "fan_duty": 100,
                "mining_time": 14334,
            }
        },
    )

    assert payload["ip"] == "192.0.2.10"
    assert payload["model"] == "Z15"
    assert payload["miner_model"] == "Z15"
    assert payload["fan_sensors"] == {
        "0": {"fan_speed": 5040},
        "1": {"fan_speed": 0},
    }
    assert payload["miner_sensors"]["average_hashrate"] == 463.97
    assert payload["miner_sensors"]["fan_duty"] == 100
    assert payload["miner_sensors"]["mining_time"] == 14334
    assert payload["mining_time"] == 14334
    assert payload["timestamp"] == "2026-07-03T12:00:00+00:00"
    json.dumps(payload)


def test_immersion_payload_uses_water_blocks_not_fans():
    """Immersion telemetry should suppress zero fan payloads."""
    module = load_publisher_module()

    payload = module.normalize_telemetry(
        "192.0.2.10",
        FakeMiner("S21+ Hydro"),
        FakeData("S21+ Hydro"),
        fan_sensors={0: {"fan_speed": 0, "fan_status": "ok"}},
        extended={
            "miner_sensors": {"cooling_mode": "immersion"},
            "board_sensors": {
                0: {
                    "inlet_water_temperature": 34,
                    "outlet_water_temperature": 45,
                    "water_temperature_delta": 11,
                }
            },
        },
    )

    assert payload["fan_sensors"] == {}
    assert payload["fans"] == []
    assert payload["board_sensors"]["0"]["water_temperature_delta"] == 11


def test_handle_payload_outputs_respects_switches(tmp_path):
    """MQTT publishing and file writing should be controlled independently."""
    module = load_publisher_module()
    payload = {"miner_model": "Z11", "value": 1}
    runtime_config = module.RuntimeConfig(
        ip="192.0.2.10",
        model_slug="z11",
        topic="miner/z11",
        web_username="root",
        web_password="root",
        exclude_config=False,
    )
    client = FakeMqttClient()

    module.PAYLOAD_FILE_DIRECTORY = str(tmp_path)
    module.PAYLOAD_FILE_PREFIX = "sample_"
    module.WRITE_PAYLOAD_FILE = True
    module.PUBLISH_TO_MQTT = False
    module.handle_payload_outputs(payload, runtime_config, mqtt_client=None)

    assert (tmp_path / "sample_z11.json").exists()

    module.WRITE_PAYLOAD_FILE = False
    module.PUBLISH_TO_MQTT = True
    module.handle_payload_outputs(payload, runtime_config, mqtt_client=client)

    assert client.messages[0][0] == "miner/z11/state"
    assert client.messages[1] == ("miner/z11/availability", "online", True)


def test_collect_telemetry_uses_detected_model_settings():
    """S21+ Hydro should use admin credentials and skip config collection."""
    module = load_publisher_module()
    miner = FakeMiner("S21+ Hydro")
    original_get_miner = module.pyasic.get_miner
    original_fetch_extended = module.fetch_extended_telemetry
    original_fetch_fan = module.fetch_fan_telemetry

    async def fake_get_miner(ip):
        assert ip == "192.0.2.10"
        return miner

    async def fake_fetch_extended(found_miner):
        assert found_miner is miner
        return {"miner_sensors": {"average_hashrate": 421.68}}

    async def fake_fetch_fan(found_miner):
        assert found_miner is miner
        return {0: {"fan_speed": 0}}

    module.pyasic.get_miner = fake_get_miner
    module.fetch_extended_telemetry = fake_fetch_extended
    module.fetch_fan_telemetry = fake_fetch_fan
    try:
        runtime_config, payload = asyncio.run(module.collect_telemetry("192.0.2.10"))
    finally:
        module.pyasic.get_miner = original_get_miner
        module.fetch_extended_telemetry = original_fetch_extended
        module.fetch_fan_telemetry = original_fetch_fan

    assert runtime_config.model_slug == "s21_plus_hydro"
    assert miner.web.username == "admin"
    assert miner.web.pwd == "admin"
    assert module.DataOptions.CONFIG in miner.exclude
    assert payload["miner_sensors"]["average_hashrate"] == 421.68
    assert payload["fan_sensors"]["0"]["fan_speed"] == 0


def test_collect_telemetry_identifies_unknown_vnish_from_extended_data():
    """Unknown VNish miners should resolve S21+ Hydro settings from /info data."""
    module = load_publisher_module()
    miner = VNish("Unknown (VNish)")
    miner.web = VNishWebAPI()
    original_get_miner = module.pyasic.get_miner
    original_fetch_extended = module.fetch_extended_telemetry
    original_fetch_fan = module.fetch_fan_telemetry
    calls = {"extended": 0}

    async def fake_get_miner(ip):
        assert ip == "192.0.2.10"
        return miner

    async def fake_fetch_extended(found_miner):
        assert found_miner is miner
        calls["extended"] += 1
        return {
            "device": {"model": "Antminer S21+ Hydro"},
            "miner_sensors": {"cooling_mode": "immersion"},
            "board_sensors": {
                0: {
                    "inlet_water_temperature": 34,
                    "outlet_water_temperature": 45,
                    "water_temperature_delta": 11,
                }
            },
        }

    async def fake_fetch_fan(found_miner):
        assert found_miner is miner
        return {0: {"fan_speed": 0}}

    module.pyasic.get_miner = fake_get_miner
    module.fetch_extended_telemetry = fake_fetch_extended
    module.fetch_fan_telemetry = fake_fetch_fan
    try:
        runtime_config, payload = asyncio.run(module.collect_telemetry("192.0.2.10"))
    finally:
        module.pyasic.get_miner = original_get_miner
        module.fetch_extended_telemetry = original_fetch_extended
        module.fetch_fan_telemetry = original_fetch_fan

    assert calls["extended"] == 1
    assert runtime_config.model_slug == "s21_plus_hydro"
    assert miner.web.username == "admin"
    assert miner.web.pwd == "admin"
    assert module.DataOptions.CONFIG in miner.exclude
    assert payload["fan_sensors"] == {}
    assert payload["board_sensors"]["0"]["water_temperature_delta"] == 11


if __name__ == "__main__":
    test_model_settings_and_file_names()
    test_normalized_payload_is_json_safe()
    test_immersion_payload_uses_water_blocks_not_fans()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_handle_payload_outputs_respects_switches(Path(tmp_dir))
    test_collect_telemetry_uses_detected_model_settings()
    test_collect_telemetry_identifies_unknown_vnish_from_extended_data()

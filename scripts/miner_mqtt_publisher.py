"""Continuously publish telemetry for a detected miner model to MQTT and/or JSON."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.util
import json
import logging
from pathlib import Path
import re
from typing import Any

import pyasic
from pyasic.miners.data import DataOptions

_LOGGER = logging.getLogger(__name__)

MINER_IP = "192.168.1.55"
INTERVAL = 10.0
VERBOSE = False

PUBLISH_TO_MQTT = True
WRITE_PAYLOAD_FILE = True

MQTT_HOST = "192.168.1.10"
MQTT_PORT = 1883
MQTT_USERNAME: str | None = None
MQTT_PASSWORD: str | None = None
MQTT_TOPIC_PREFIX = "miner"

DEFAULT_WEB_USERNAME = "root"
DEFAULT_WEB_PASSWORD = "root"

PAYLOAD_FILE_DIRECTORY = "."
PAYLOAD_FILE_PREFIX = ""

MODEL_SETTINGS: dict[str, dict[str, Any]] = {
    "z11": {
        "topic": "miner/z11",
        "web_username": "root",
        "web_password": "root",
        "exclude_config": False,
    },
    "z15": {
        "topic": "miner/z15",
        "web_username": "root",
        "web_password": "root",
        "exclude_config": False,
    },
    "s21_plus_hydro": {
        "topic": "miner/s21_plus_hydro",
        "web_username": "admin",
        "web_password": "admin",
        "exclude_config": True,
    },
}

_FAN_TELEMETRY_MODULE: Any | None = None
_VNISH_TELEMETRY_MODULE: Any | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved runtime settings for one detected miner."""

    ip: str
    model_slug: str
    topic: str
    web_username: str | None
    web_password: str | None
    exclude_config: bool


def configure_logging() -> None:
    """Configure console logging from file-level settings."""
    logging.basicConfig(
        level=logging.DEBUG if VERBOSE else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_module(name: str, filename: str) -> Any:
    """Load an integration helper without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        msg = f"Unable to load {module_path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_vnish_telemetry_module() -> Any:
    """Load the shared VNish telemetry helper once."""
    global _VNISH_TELEMETRY_MODULE  # noqa: PLW0603
    if _VNISH_TELEMETRY_MODULE is None:
        _VNISH_TELEMETRY_MODULE = load_module(
            "miner_vnish_telemetry", "vnish_telemetry.py"
        )
    return _VNISH_TELEMETRY_MODULE


def load_fan_telemetry_module() -> Any:
    """Load the shared fan telemetry helper once."""
    global _FAN_TELEMETRY_MODULE  # noqa: PLW0603
    if _FAN_TELEMETRY_MODULE is None:
        _FAN_TELEMETRY_MODULE = load_module("miner_fan_telemetry", "fan_telemetry.py")
    return _FAN_TELEMETRY_MODULE


def apply_pyasic_compat() -> None:
    """Apply fork-local pyasic compatibility patches."""
    compat = load_module("miner_pyasic_compat", "pyasic_compat.py")
    compat.apply_pyasic_compat(pyasic)


def _clean(value: Any) -> Any:
    """Return JSON-safe data while preserving useful scalar values."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_clean(item) for item in value]
    if hasattr(value, "model_dump"):
        return _clean(value.model_dump(mode="json"))
    if hasattr(value, "as_dict"):
        return _clean(value.as_dict())
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _data_dict(data: Any) -> dict[str, Any]:
    """Convert pyasic data to a dictionary with computed fields included."""
    if hasattr(data, "model_dump"):
        dumped = data.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if hasattr(data, "as_dict"):
        dumped = data.as_dict()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(data, "dict"):
        dumped = data.dict()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _first_value(raw: Mapping[str, Any], data: Any, *names: str) -> Any:
    """Return the first non-empty value from raw data or attributes."""
    for name in names:
        if name in raw and raw[name] not in (None, ""):
            return _clean(raw[name])
        value = getattr(data, name, None)
        if value not in (None, ""):
            return _clean(value)
    return None


def _unknown_model(value: Any) -> bool:
    """Return true when pyasic only provided an unknown placeholder model."""
    return value in (None, "") or str(value).lower().startswith("unknown")


def _generic_firmware(value: Any) -> bool:
    """Return true when firmware is missing or only names the firmware family."""
    return value in (None, "") or str(value).lower() in {"vnish"}


def _slugify_model(value: Any) -> str:
    """Return a stable model slug for topics and file names."""
    text = str(value or "").strip().lower()
    generic = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if generic in {"unknown", "unknown_vnish", "vnish"}:
        return "unknown"
    if "z11" in text:
        return "z11"
    if "z15" in text:
        return "z15"
    if "s21" in text and "hydro" in text:
        return "s21_plus_hydro"
    text = text.replace("+", " plus ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def model_slug_from_miner(miner: Any) -> str:
    """Return model slug from pyasic miner metadata."""
    for value in (
        getattr(miner, "model", None),
        getattr(miner, "raw_model", None),
        getattr(miner, "name", None),
        miner.__class__.__name__,
    ):
        slug = _slugify_model(value)
        if slug != "unknown":
            return slug
    return "unknown"


def model_slug_from_payload(payload: Mapping[str, Any]) -> str:
    """Return model slug from the normalized payload."""
    device = payload.get("device")
    if not isinstance(device, Mapping):
        device = {}
    for value in (
        payload.get("miner_model"),
        payload.get("model"),
        device.get("model"),
        payload.get("class"),
    ):
        slug = _slugify_model(value)
        if slug != "unknown":
            return slug
    return "unknown"


def resolve_runtime_config(miner: Any, *, ip: str = MINER_IP) -> RuntimeConfig:
    """Resolve topic and credentials from the detected miner model."""
    return runtime_config_from_model_slug(model_slug_from_miner(miner), ip=ip)


def runtime_config_from_model_slug(model_slug: str, *, ip: str = MINER_IP) -> RuntimeConfig:
    """Resolve topic and credentials from a normalized model slug."""
    settings = MODEL_SETTINGS.get(model_slug, {})
    topic = str(settings.get("topic") or f"{MQTT_TOPIC_PREFIX.rstrip('/')}/{model_slug}")
    web_username = settings.get("web_username", DEFAULT_WEB_USERNAME)
    web_password = settings.get("web_password", DEFAULT_WEB_PASSWORD)
    return RuntimeConfig(
        ip=ip,
        model_slug=model_slug,
        topic=topic,
        web_username=web_username,
        web_password=web_password,
        exclude_config=bool(settings.get("exclude_config", False)),
    )


def _is_unknown_vnish_miner(miner: Any, runtime_config: RuntimeConfig) -> bool:
    """Return true when pyasic did not identify a VNish miner model."""
    if runtime_config.model_slug not in {"unknown", "vnish"}:
        return False
    web = getattr(miner, "web", None)
    return "VNISH" in str(web.__class__.__name__).upper()


def payload_file_path(payload: Mapping[str, Any]) -> Path:
    """Return payload file path using the detected model slug."""
    model_slug = model_slug_from_payload(payload)
    return Path(PAYLOAD_FILE_DIRECTORY) / f"{PAYLOAD_FILE_PREFIX}{model_slug}.json"


def create_mqtt_client() -> Any:
    """Create, configure, and connect a paho-mqtt client."""
    try:
        from paho.mqtt import client as mqtt_client
    except ImportError as err:
        msg = "Install paho-mqtt to publish telemetry to MQTT."
        raise RuntimeError(msg) from err

    client_id = f"hass-miner-{MINER_IP.replace('.', '-')}"
    if hasattr(mqtt_client, "CallbackAPIVersion"):
        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
    else:
        client = mqtt_client.Client(client_id=client_id)

    if MQTT_USERNAME is not None:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def publish_text(client: Any, topic: str, payload: str, *, retain: bool = True) -> None:
    """Publish a retained text payload and fail on rejected publish calls."""
    result = client.publish(topic, payload, retain=retain)
    rc = getattr(result, "rc", 0)
    if int(rc) != 0:
        msg = f"MQTT publish failed for {topic}: rc={rc}"
        raise RuntimeError(msg)


def publish_json(client: Any, topic: str, payload: Mapping[str, Any]) -> None:
    """Publish a retained JSON payload."""
    publish_text(
        client,
        topic,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        retain=True,
    )


def write_json_file(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write telemetry JSON to a file."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def set_miner_credentials(
    miner: Any, *, web_username: str | None, web_password: str | None
) -> None:
    """Set miner web credentials when a web backend exists."""
    web = getattr(miner, "web", None)
    if web is None:
        return
    if web_username is not None:
        web.username = web_username
    if web_password is not None:
        web.pwd = web_password


def _merge_extended_telemetry(
    payload: dict[str, Any], extended: Mapping[str, Any] | None
) -> None:
    """Merge integration-style extended telemetry into the MQTT payload."""
    extended = extended or {}
    device = extended.get("device")
    if not isinstance(device, Mapping):
        device = {}

    if payload.get("make") in (None, ""):
        payload["make"] = _clean(device.get("make"))
    if _unknown_model(payload.get("model")):
        payload["model"] = _clean(device.get("model"))
    if _generic_firmware(payload.get("firmware")):
        payload["firmware"] = _clean(device.get("fw_ver"))
    if payload.get("mac") in (None, ""):
        payload["mac"] = _clean(device.get("mac"))

    payload["device"] = _clean(device)
    payload["miner_sensors"] = _clean(extended.get("miner_sensors", {}))
    payload["board_sensors"] = _clean(extended.get("board_sensors", {}))
    payload["fan_sensors"] = _clean(extended.get("fan_sensors", {}))
    payload["sensor_attributes"] = _clean(extended.get("sensor_attributes", {}))


def _merge_fan_telemetry(
    payload: dict[str, Any], fan_sensors: Mapping[int, Mapping[str, Any]] | None
) -> None:
    """Merge corrected fan sensors into the MQTT payload."""
    if not fan_sensors:
        return

    existing = payload.get("fan_sensors")
    if not isinstance(existing, Mapping):
        existing = {}
    merged = {str(fan): dict(sensors) for fan, sensors in existing.items()}
    for fan, sensors in fan_sensors.items():
        key = str(fan)
        target = merged.setdefault(key, {})
        for sensor, value in sensors.items():
            target[sensor] = _clean(value)

    payload["fan_sensors"] = merged
    payload["fans"] = [
        {"speed": sensors.get("fan_speed")}
        for _, sensors in sorted(merged.items(), key=lambda item: int(item[0]))
        if "fan_speed" in sensors
    ]


def _uses_immersion_cooling(payload: Mapping[str, Any]) -> bool:
    """Return true when telemetry should be shown as water cooling blocks."""
    miner_sensors = payload.get("miner_sensors")
    if not isinstance(miner_sensors, Mapping):
        return False
    mode = str(miner_sensors.get("cooling_mode", "")).lower()
    return mode in {"immersion", "immers"}


def normalize_telemetry(
    ip: str,
    miner: Any,
    data: Any,
    *,
    now: datetime | None = None,
    extended: Mapping[str, Any] | None = None,
    fan_sensors: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize pyasic telemetry into a stable MQTT payload."""
    raw = _data_dict(data)
    collected_at = now or datetime.now(UTC)
    payload = {
        "ip": ip,
        "class": miner.__class__.__name__,
        "make": _first_value(raw, data, "make"),
        "model": _first_value(raw, data, "model"),
        "miner_model": _clean(getattr(miner, "model", None)),
        "firmware": _first_value(raw, data, "firmware", "fw_ver"),
        "mac": _first_value(raw, data, "mac"),
        "is_mining": _first_value(raw, data, "is_mining"),
        "uptime": _first_value(raw, data, "uptime"),
        "hashrate": _first_value(raw, data, "hashrate", "raw_hashrate"),
        "hashboards": _first_value(raw, data, "hashboards"),
        "fans": _first_value(raw, data, "fans"),
        "temperature": {
            "env": _first_value(raw, data, "env_temp"),
            "average": _first_value(raw, data, "temperature_avg"),
        },
        "power": {
            "wattage": _first_value(raw, data, "wattage"),
            "voltage": _first_value(raw, data, "voltage"),
            "wattage_limit": _first_value(
                raw, data, "wattage_limit", "raw_wattage_limit"
            ),
        },
        "timestamp": collected_at.isoformat(),
    }
    _merge_extended_telemetry(payload, extended)
    if _uses_immersion_cooling(payload):
        payload["fan_sensors"] = {}
        payload["fans"] = []
    else:
        _merge_fan_telemetry(payload, fan_sensors)
    return payload


async def fetch_extended_telemetry(miner: Any) -> dict[str, Any]:
    """Fetch integration-style extended telemetry when the firmware supports it."""
    vnish_telemetry = load_vnish_telemetry_module()
    return await vnish_telemetry.fetch_vnish_extended_data(miner)


async def fetch_fan_telemetry(miner: Any) -> dict[int, dict[str, int]]:
    """Fetch corrected fan telemetry directly from RPC stats."""
    fan_telemetry = load_fan_telemetry_module()
    return await fan_telemetry.fetch_rpc_fan_sensors(miner)


async def collect_telemetry(ip: str = MINER_IP) -> tuple[RuntimeConfig, dict[str, Any]]:
    """Read one telemetry sample from the miner."""
    miner = await pyasic.get_miner(ip)
    if miner is None:
        msg = f"No miner detected at {ip}"
        raise RuntimeError(msg)

    runtime_config = resolve_runtime_config(miner, ip=ip)
    extended: dict[str, Any] | None = None
    if _is_unknown_vnish_miner(miner, runtime_config):
        set_miner_credentials(
            miner,
            web_username="admin",
            web_password="admin",
        )
        extended = await fetch_extended_telemetry(miner)
        detected_slug = model_slug_from_payload(
            {
                "device": extended.get("device", {}),
                "class": miner.__class__.__name__,
            }
        )
        runtime_config = runtime_config_from_model_slug(detected_slug, ip=ip)

    set_miner_credentials(
        miner,
        web_username=runtime_config.web_username,
        web_password=runtime_config.web_password,
    )

    if runtime_config.exclude_config:
        data = await miner.get_data(exclude=[DataOptions.CONFIG])
    else:
        data = await miner.get_data()

    if extended is None:
        extended = await fetch_extended_telemetry(miner)
    fan_sensors = await fetch_fan_telemetry(miner)
    payload = normalize_telemetry(
        ip,
        miner,
        data,
        extended=extended,
        fan_sensors=fan_sensors,
    )
    return runtime_config, payload


def handle_payload_outputs(
    payload: Mapping[str, Any],
    runtime_config: RuntimeConfig,
    *,
    mqtt_client: Any | None,
) -> None:
    """Write and publish the payload based on file-level switches."""
    if WRITE_PAYLOAD_FILE:
        output_path = payload_file_path(payload)
        write_json_file(output_path, payload)
        _LOGGER.info("Wrote %s", output_path)

    if PUBLISH_TO_MQTT:
        if mqtt_client is None:
            msg = "MQTT publishing is enabled but no client is connected."
            raise RuntimeError(msg)
        state_topic = f"{runtime_config.topic.rstrip('/')}/state"
        availability_topic = f"{runtime_config.topic.rstrip('/')}/availability"
        publish_json(mqtt_client, state_topic, payload)
        publish_text(mqtt_client, availability_topic, "online")
        _LOGGER.info("Published %s telemetry to %s", runtime_config.model_slug, state_topic)


async def run() -> None:
    """Run the continuous publish/write loop."""
    apply_pyasic_compat()
    client = create_mqtt_client() if PUBLISH_TO_MQTT else None
    last_availability_topic: str | None = None

    try:
        while True:
            try:
                runtime_config, payload = await collect_telemetry(MINER_IP)
                last_availability_topic = (
                    f"{runtime_config.topic.rstrip('/')}/availability"
                )
                handle_payload_outputs(payload, runtime_config, mqtt_client=client)
            except Exception:
                _LOGGER.exception("Unable to collect or publish miner telemetry")
                if client is not None and last_availability_topic is not None:
                    with contextlib.suppress(Exception):
                        publish_text(client, last_availability_topic, "offline")
            await asyncio.sleep(INTERVAL)
    finally:
        if client is not None and last_availability_topic is not None:
            with contextlib.suppress(Exception):
                publish_text(client, last_availability_topic, "offline")
        if client is not None:
            with contextlib.suppress(Exception):
                client.loop_stop()
            with contextlib.suppress(Exception):
                client.disconnect()


def main() -> None:
    """Run the file-configured entrypoint."""
    configure_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        _LOGGER.info("Stopped")


if __name__ == "__main__":
    main()

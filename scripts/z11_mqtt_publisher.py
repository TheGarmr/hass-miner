"""Continuously publish Antminer Z11 telemetry to MQTT."""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
import contextlib
from datetime import UTC, datetime
import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any

import pyasic

_LOGGER = logging.getLogger(__name__)
DEFAULT_INTERVAL = 30.0
DEFAULT_MQTT_PORT = 1883
DEFAULT_TOPIC = "miner/z11"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Continuously publish Antminer Z11 telemetry to MQTT."
    )
    parser.add_argument("ip", help="Antminer Z11 IP address")
    parser.add_argument("--mqtt-host", required=True, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--mqtt-username")
    parser.add_argument("--mqtt-password")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument(
        "--web-username",
        default=os.environ.get("MINER_WEB_USERNAME", "root"),
    )
    parser.add_argument(
        "--web-password",
        default=os.environ.get("MINER_WEB_PASSWORD", "root"),
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    return build_parser().parse_args(argv)


def configure_logging(verbose: bool) -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
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


def apply_pyasic_compat() -> None:
    """Apply fork-local pyasic compatibility patches."""
    compat = load_module("miner_pyasic_compat", "pyasic_compat.py")
    compat.apply_pyasic_compat(pyasic)


def create_mqtt_client(args: argparse.Namespace) -> Any:
    """Create, configure, and connect a paho-mqtt client."""
    try:
        from paho.mqtt import client as mqtt_client
    except ImportError as err:
        msg = "Install paho-mqtt to publish telemetry to MQTT."
        raise RuntimeError(msg) from err

    client_id = f"hass-miner-z11-{args.ip.replace('.', '-')}"
    if hasattr(mqtt_client, "CallbackAPIVersion"):
        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
    else:
        client = mqtt_client.Client(client_id=client_id)

    if args.mqtt_username is not None:
        client.username_pw_set(args.mqtt_username, args.mqtt_password)

    client.connect(args.mqtt_host, args.mqtt_port, keepalive=60)
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


def set_miner_credentials(
    miner: Any, *, web_username: str | None, web_password: str | None
) -> None:
    """Set old Antminer web credentials when a web backend exists."""
    web = getattr(miner, "web", None)
    if web is None:
        return
    if web_username is not None:
        web.username = web_username
    if web_password is not None:
        web.pwd = web_password


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


def normalize_telemetry(
    ip: str, miner: Any, data: Any, *, now: datetime | None = None
) -> dict[str, Any]:
    """Normalize pyasic telemetry into a stable MQTT payload."""
    raw = _data_dict(data)
    collected_at = now or datetime.now(UTC)
    return {
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


async def collect_telemetry(args: argparse.Namespace) -> dict[str, Any]:
    """Read one telemetry sample from the miner."""
    miner = await pyasic.get_miner(args.ip)
    if miner is None:
        msg = f"No miner detected at {args.ip}"
        raise RuntimeError(msg)

    set_miner_credentials(
        miner,
        web_username=args.web_username,
        web_password=args.web_password,
    )
    data = await miner.get_data()
    return normalize_telemetry(args.ip, miner, data)


async def run(args: argparse.Namespace) -> None:
    """Run the continuous MQTT publish loop."""
    apply_pyasic_compat()
    state_topic = f"{args.topic.rstrip('/')}/state"
    availability_topic = f"{args.topic.rstrip('/')}/availability"
    client = create_mqtt_client(args)

    try:
        publish_text(client, availability_topic, "offline")
        while True:
            try:
                payload = await collect_telemetry(args)
                publish_json(client, state_topic, payload)
                publish_text(client, availability_topic, "online")
                _LOGGER.info("Published Z11 telemetry to %s", state_topic)
            except Exception:
                _LOGGER.exception("Unable to publish Z11 telemetry")
                with contextlib.suppress(Exception):
                    publish_text(client, availability_topic, "offline")
            await asyncio.sleep(args.interval)
    finally:
        with contextlib.suppress(Exception):
            publish_text(client, availability_topic, "offline")
        with contextlib.suppress(Exception):
            client.loop_stop()
        with contextlib.suppress(Exception):
            client.disconnect()


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI entrypoint."""
    args = parse_args(argv)
    configure_logging(args.verbose)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        _LOGGER.info("Stopped")


if __name__ == "__main__":
    main()

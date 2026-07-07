"""VNish-specific telemetry helpers for miner coordinator data."""
from __future__ import annotations

import logging
from typing import Any

try:
    from .voltage_telemetry import normalize_voltage
except ImportError:  # pragma: no cover - used by standalone MQTT scripts
    import importlib.util
    from pathlib import Path

    module_path = Path(__file__).with_name("voltage_telemetry.py")
    spec = importlib.util.spec_from_file_location("miner_voltage_telemetry", module_path)
    voltage_module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise
    spec.loader.exec_module(voltage_module)
    normalize_voltage = voltage_module.normalize_voltage

_LOGGER = logging.getLogger(__name__)
GIGA_HASH_PER_TERA_HASH = 1000


async def fetch_vnish_extended_data(miner: Any) -> dict[str, Any]:
    """Fetch and normalize read-only VNish Web API telemetry."""
    if "VNISH" not in str(miner.__class__.__name__).upper() and "VNISH" not in str(
        getattr(miner, "firmware", "")
    ).upper():
        return {}

    web = getattr(miner, "web", None)
    if web is None:
        return {}

    payloads = {}
    for key, method_name in (
        ("summary", "summary"),
        ("chips", "chips"),
        ("perf_summary", "perf_summary"),
        ("info", "info"),
        ("settings", "settings"),
    ):
        method = getattr(web, method_name, None)
        if not callable(method):
            continue
        try:
            payloads[key] = await method()
        except Exception as err:
            _LOGGER.debug("%s: unable to fetch VNish %s: %s", miner, key, err)

    if not payloads:
        return {}

    return normalize_vnish_extended_data(
        summary=payloads.get("summary"),
        chips=payloads.get("chips"),
        perf_summary=payloads.get("perf_summary"),
        info=payloads.get("info"),
        settings=payloads.get("settings"),
    )


def normalize_vnish_extended_data(
    *,
    summary: dict[str, Any] | None,
    chips: dict[str, Any] | None,
    perf_summary: dict[str, Any] | None,
    info: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize VNish Web API payloads into coordinator data fragments."""
    miner = summary.get("miner", {}) if isinstance(summary, dict) else {}
    chains = miner.get("chains", []) if isinstance(miner, dict) else []
    cooling = miner.get("cooling", {}) if isinstance(miner, dict) else {}
    settings_miner = settings.get("miner", {}) if isinstance(settings, dict) else {}
    settings_cooling = (
        settings_miner.get("cooling", {}) if isinstance(settings_miner, dict) else {}
    )
    chip_summary = _chip_summary(chips)

    data: dict[str, Any] = {
        "device": _device_info(info, miner),
        "miner_sensors": _miner_sensors(
            miner,
            perf_summary,
            chip_summary,
            settings_cooling,
        ),
        "board_sensors": _board_sensors(chains),
        "fan_sensors": _fan_sensors(cooling),
        "cooling": _cooling_info(cooling, settings_cooling),
        "sensor_attributes": {},
    }

    return data


def _device_info(info: dict[str, Any] | None, miner: dict[str, Any]) -> dict[str, Any]:
    """Return device identity fallback data from VNish payloads."""
    info = info or {}
    system = _dict(info.get("system"))
    network = _dict(system.get("network_status"))
    fw_name = info.get("fw_name")
    fw_version = info.get("fw_version")
    firmware = " ".join(str(value) for value in (fw_name, fw_version) if value)
    model = info.get("miner") or miner.get("miner_type")
    make = "Antminer" if model and "antminer" in str(model).lower() else None
    return {
        "hostname": network.get("hostname"),
        "mac": network.get("mac"),
        "make": make,
        "model": model,
        "fw_ver": firmware or fw_version or fw_name,
    }


def _miner_sensors(
    miner: dict[str, Any],
    perf_summary: dict[str, Any] | None,
    chip_summary: dict[str, Any],
    settings_cooling: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build miner-level sensors from VNish summary payloads."""
    pcb_temp = _dict(miner.get("pcb_temp"))
    chip_temp = _dict(miner.get("chip_temp"))
    cooling = _dict(miner.get("cooling"))
    cooling_settings = _dict(cooling.get("settings"))
    cooling_mode = _dict(cooling_settings.get("mode"))
    settings_cooling = _dict(settings_cooling)
    chains = miner.get("chains", [])
    current_preset = _dict((perf_summary or {}).get("current_preset"))
    cooling_mode_name = _normalize_cooling_mode(
        cooling_mode.get("name")
        or _dict(settings_cooling.get("mode")).get("name")
    )
    sensor_data = {
        "temperature": _number(chip_temp.get("max")),
        "instant_hashrate": _number(miner.get("instant_hashrate")),
        "average_hashrate": _number(miner.get("average_hashrate")),
        "nominal_hashrate": _gh_to_th(miner.get("hr_nominal")),
        "stock_hashrate": _gh_to_th(miner.get("hr_stock")),
        "power_efficiency": _number(miner.get("power_efficiency")),
        "cooling_mode": cooling_mode_name,
        "fan_duty": _number(cooling.get("fan_duty")),
        "cooling_min_fan_duty": _number(settings_cooling.get("fan_min_duty")),
        "cooling_max_fan_duty": _number(settings_cooling.get("fan_max_duty")),
        "minimum_startup_water_temperature": _number(
            settings_cooling.get("min_startup_water_temp")
        ),
        "hw_errors": _int(miner.get("hw_errors")),
        "hw_errors_percent": _number(miner.get("hw_errors_percent")),
        "devfee_percent": _number(miner.get("devfee_percent")),
        "pcb_temperature_min": _number(pcb_temp.get("min")),
        "pcb_temperature_max": _number(pcb_temp.get("max")),
        "chip_temperature_min": _number(chip_temp.get("min")),
        "chip_temperature_max": _number(chip_temp.get("max")),
        "water_inlet_temperature_min": _min_chain_value(chains, "inlet_water_temp"),
        "water_inlet_temperature_max": _max_chain_value(chains, "inlet_water_temp"),
        "water_outlet_temperature_min": _min_chain_value(chains, "outlet_water_temp"),
        "water_outlet_temperature_max": _max_chain_value(chains, "outlet_water_temp"),
        "current_preset": current_preset.get("pretty") or current_preset.get("name"),
        "total_chips": chip_summary.get("total_chips"),
        "bad_chips": chip_summary.get("bad_chips"),
        "chip_errors": chip_summary.get("chip_errors"),
        "chip_detail": chip_summary.get("total_chips"),
    }
    return {key: value for key, value in sensor_data.items() if value is not None}


def _board_sensors(chains: list[Any]) -> dict[int, dict[str, Any]]:
    """Build per-board sensors from VNish summary chains."""
    boards = {}
    for index, chain in enumerate(chains):
        if not isinstance(chain, dict):
            continue
        slot = _int(chain.get("id"))
        if slot is None:
            slot = index
        else:
            slot -= 1
        pcb_temp = _dict(chain.get("pcb_temp"))
        chip_temp = _dict(chain.get("chip_temp"))
        statuses = _dict(chain.get("chip_statuses"))
        inlet_water_temperature = _number(chain.get("inlet_water_temp"))
        outlet_water_temperature = _number(chain.get("outlet_water_temp"))
        data = {
            "board_temperature": _number(pcb_temp.get("max")),
            "chip_temperature": _number(chip_temp.get("max")),
            "board_hashrate": _gh_to_th(chain.get("hashrate_rt")),
            "board_hashrate_ideal": _gh_to_th(chain.get("hashrate_ideal")),
            "board_hashrate_percentage": _number(chain.get("hashrate_percentage")),
            "board_frequency": _number(chain.get("frequency")),
            "board_voltage": _millivolts_to_volts(chain.get("voltage")),
            "board_power": _number(chain.get("power_consumption")),
            "board_hw_errors": _int(chain.get("hw_errors")),
            "board_hr_error": _number(chain.get("hr_error")),
            "board_pcb_temperature_min": _number(pcb_temp.get("min")),
            "board_pcb_temperature_max": _number(pcb_temp.get("max")),
            "board_chip_temperature_min": _number(chip_temp.get("min")),
            "board_chip_temperature_max": _number(chip_temp.get("max")),
            "inlet_water_temperature": inlet_water_temperature,
            "outlet_water_temperature": outlet_water_temperature,
            "water_temperature_delta": _temperature_delta(
                inlet_water_temperature,
                outlet_water_temperature,
            ),
            "chip_status_red": _int(statuses.get("red")),
            "chip_status_orange": _int(statuses.get("orange")),
            "chip_status_grey": _int(statuses.get("grey")),
        }
        boards[slot] = {key: value for key, value in data.items() if value is not None}
    return boards


def _cooling_info(
    cooling: dict[str, Any],
    settings_cooling: dict[str, Any],
) -> dict[str, Any]:
    """Return compact cooling metadata for coordinator decisions."""
    cooling = _dict(cooling)
    settings_cooling = _dict(settings_cooling)
    summary_mode = _dict(_dict(cooling.get("settings")).get("mode")).get("name")
    settings_mode = _dict(settings_cooling.get("mode")).get("name")
    data = {
        "mode": _normalize_cooling_mode(summary_mode or settings_mode),
        "fan_count": _int(cooling.get("fan_num")),
    }
    return {key: value for key, value in data.items() if value is not None}


def _fan_sensors(cooling: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Build fan sensors from VNish cooling payload."""
    fans = {}
    for index, fan in enumerate(cooling.get("fans", []) if cooling else []):
        if not isinstance(fan, dict):
            continue
        fan_id = _int(fan.get("id"))
        if fan_id is None:
            fan_id = index
        data = {
            "fan_speed": _int(fan.get("rpm")),
            "fan_status": fan.get("status"),
            "fan_max_speed": _int(fan.get("max_rpm")),
        }
        fans[fan_id] = {key: value for key, value in data.items() if value is not None}
    return fans


def _chip_summary(chips: dict[str, Any] | None) -> dict[str, Any]:
    """Build a compact chip summary without the full per-chip map."""
    if not isinstance(chips, dict):
        return {}
    chains = chips.get("chains", [])
    total_chips = 0
    bad_chips = 0
    chip_errors = 0
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        chain_chips = chain.get("chips", [])
        if not isinstance(chain_chips, list):
            continue
        total_chips += len(chain_chips)
        for chip in chain_chips:
            if not isinstance(chip, dict):
                continue
            status = str(chip.get("status", "")).lower()
            if status in {"red", "orange"}:
                bad_chips += 1
            chip_errors += _int(chip.get("errors")) or 0
    return {
        "chips_per_chain": chips.get("chips_per_chain"),
        "total_chips": total_chips,
        "bad_chips": bad_chips,
        "chip_errors": chip_errors,
    }


def _dict(value: Any) -> dict[str, Any]:
    """Return value when it is a dict, otherwise an empty dict."""
    if isinstance(value, dict):
        return value
    return {}


def _number(value: Any) -> float | None:
    """Return value as float when possible."""
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    """Return value as int when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _gh_to_th(value: Any) -> float | None:
    """Convert GH/s value to TH/s."""
    number = _number(value)
    if number is None:
        return None
    return round(number / GIGA_HASH_PER_TERA_HASH, 2)


def _millivolts_to_volts(value: Any) -> float | None:
    """Convert VNish chain voltage to V."""
    return normalize_voltage(value)


def _temperature_delta(inlet: float | None, outlet: float | None) -> float | None:
    """Return outlet-minus-inlet temperature delta."""
    if inlet is None or outlet is None:
        return None
    return round(outlet - inlet, 2)


def _normalize_cooling_mode(value: Any) -> str | None:
    """Return stable cooling mode names across VNish payloads."""
    if value is None:
        return None
    mode = str(value).strip().lower()
    if mode == "immers":
        return "immersion"
    return mode or None


def _chain_values(chains: Any, key: str) -> list[float]:
    """Extract numeric chain values for min/max helpers."""
    if not isinstance(chains, list):
        return []
    values = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        value = _number(chain.get(key))
        if value is not None:
            values.append(value)
    return values


def _min_chain_value(chains: Any, key: str) -> float | None:
    """Return minimum numeric chain value."""
    values = _chain_values(chains, key)
    return min(values) if values else None


def _max_chain_value(chains: Any, key: str) -> float | None:
    """Return maximum numeric chain value."""
    values = _chain_values(chains, key)
    return max(values) if values else None

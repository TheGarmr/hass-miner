"""Miner DataUpdateCoordinator."""
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyasic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_IP
from .const import CONF_MIN_POWER
from .const import CONF_MAX_POWER
from .const import CONF_RPC_PASSWORD
from .const import CONF_SSH_PASSWORD
from .const import CONF_SSH_USERNAME
from .const import CONF_WEB_PASSWORD
from .const import CONF_WEB_USERNAME
from .entity_helpers import resolved_model
from .entity_helpers import stable_device_id
from .fan_telemetry import fetch_rpc_fan_sensors
from .fan_telemetry import merge_fan_sensors
from .hashrate_telemetry import TERA_HASH_PER_SECOND
from .hashrate_telemetry import miner_hashrate_unit
from .hashrate_telemetry import normalize_hashrate
from .vnish_telemetry import fetch_vnish_extended_data

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5

DEFAULT_DATA = {
    "hostname": None,
    "mac": None,
    "device_id": None,
    "make": None,
    "model": None,
    "ip": None,
    "is_mining": False,
    "fw_ver": None,
    "miner_sensors": {
        "hashrate": 0,
        "ideal_hashrate": 0,
        "active_preset_name": None,
        "temperature": 0,
        "power_limit": 0,
        "miner_consumption": 0,
        "efficiency": 0.0,
    },
    "board_sensors": {},
    "fan_sensors": {},
    "sensor_attributes": {},
    "sensor_units": {},
    "config": {},
}


def _generic_firmware(value):
    """Return true when firmware is missing or only names the firmware family."""
    return value in (None, "") or str(value).lower() in {"vnish"}


def _uses_vnish_water_cooling(vnish_data):
    """Return true when VNish reports hydro/immersion cooling blocks."""
    cooling_mode = str(vnish_data.get("cooling", {}).get("mode", "")).lower()
    return cooling_mode in {"immersion", "immers"}


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the Miner."""

    miner: "pyasic.AnyMiner" = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.miner = None
        self._failure_count = 0
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=10),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

    @property
    def available(self):
        """Return if device is available or not."""
        return self.miner is not None

    def _zeroed_data(self):
        """Return zeroed data while keeping hashrate units stable."""
        data = {
            **DEFAULT_DATA,
            "power_limit_range": {
                "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
            },
        }
        preferred_hashrate_unit = miner_hashrate_unit(self.miner)
        if preferred_hashrate_unit is not None:
            data["sensor_units"] = {
                "hashrate": preferred_hashrate_unit,
                "ideal_hashrate": preferred_hashrate_unit,
                "board_hashrate": preferred_hashrate_unit,
            }
        return data

    async def get_miner(self):
        """Get a valid Miner instance."""
        import pyasic  # lazy import to avoid blocking event loop

        miner_ip = self.config_entry.data[CONF_IP]
        miner = await pyasic.get_miner(miner_ip)
        if miner is None:
            return None

        self.miner = miner
        if self.miner.api is not None:
            if self.miner.api.pwd is not None:
                self.miner.api.pwd = self.config_entry.data.get(CONF_RPC_PASSWORD, "")

        if self.miner.web is not None:
            self.miner.web.username = self.config_entry.data.get(CONF_WEB_USERNAME, "")
            self.miner.web.pwd = self.config_entry.data.get(CONF_WEB_PASSWORD, "")

        if self.miner.ssh is not None:
            self.miner.ssh.username = self.config_entry.data.get(CONF_SSH_USERNAME, "")
            self.miner.ssh.pwd = self.config_entry.data.get(CONF_SSH_PASSWORD, "")
        return self.miner

    async def _async_update_data(self):
        """Fetch sensors from miners."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = await self.get_miner()

        if miner is None:
            self._failure_count += 1

            if self._failure_count == 1:
                _LOGGER.warning(
                    "Miner is offline – returning zeroed data (first failure)."
                )
                return self._zeroed_data()

            raise UpdateFailed("Miner Offline (consecutive failure)")

        # At this point, miner is valid
        _LOGGER.debug(f"Found miner: {self.miner}")

        # Base data options to fetch
        data_options = [
            pyasic.DataOptions.HOSTNAME,
            pyasic.DataOptions.MAC,
            pyasic.DataOptions.IS_MINING,
            pyasic.DataOptions.FW_VERSION,
            pyasic.DataOptions.HASHRATE,
            pyasic.DataOptions.EXPECTED_HASHRATE,
            pyasic.DataOptions.HASHBOARDS,
            pyasic.DataOptions.WATTAGE,
            pyasic.DataOptions.WATTAGE_LIMIT,
            pyasic.DataOptions.FANS,
            pyasic.DataOptions.CONFIG,
        ]

        try:
            miner_data = await self.miner.get_data(include=data_options)
        except Exception as err:
            # VNish firmware has a bug with CONFIG - retry without it
            if "config" in str(err).lower():
                _LOGGER.warning(
                    f"Config fetch failed for {self.miner}, retrying without CONFIG: {err}"
                )
                data_options.remove(pyasic.DataOptions.CONFIG)
                try:
                    miner_data = await self.miner.get_data(include=data_options)
                except Exception as retry_err:
                    self._failure_count += 1
                    if self._failure_count == 1:
                        _LOGGER.warning(
                            f"Error fetching miner data: {retry_err} – returning zeroed data (first failure)."
                        )
                        return self._zeroed_data()
                    _LOGGER.exception(retry_err)
                    raise UpdateFailed from retry_err
            else:
                self._failure_count += 1

                if self._failure_count == 1:
                    _LOGGER.warning(
                        f"Error fetching miner data: {err} – returning zeroed data (first failure)."
                    )
                    return self._zeroed_data()

                _LOGGER.exception(err)
                raise UpdateFailed from err

        _LOGGER.debug(f"Got data: {miner_data}")

        # Success: reset the failure count
        self._failure_count = 0

        vnish_data = await fetch_vnish_extended_data(self.miner)
        vnish_device = vnish_data.get("device", {})

        normalized_hashrate = normalize_hashrate(miner_data.hashrate)
        normalized_expected_hashrate = normalize_hashrate(miner_data.expected_hashrate)
        preferred_hashrate_unit = miner_hashrate_unit(self.miner)
        sensor_units = {
            sensor: unit
            for sensor, unit in (
                ("hashrate", normalized_hashrate.unit),
                ("ideal_hashrate", normalized_expected_hashrate.unit),
            )
            if unit is not None
        }
        if preferred_hashrate_unit is not None:
            sensor_units["hashrate"] = preferred_hashrate_unit
            sensor_units["ideal_hashrate"] = preferred_hashrate_unit

        try:
            active_preset = miner_data.config.mining_mode.active_preset.name
        except AttributeError:
            active_preset = None

        miner_ip = str(self.miner.ip)
        mac = miner_data.mac or vnish_device.get("mac")
        hostname = miner_data.hostname or vnish_device.get("hostname")
        device_id = stable_device_id(miner_ip, mac)
        model = resolved_model(self.miner, miner_data.model) or vnish_device.get("model")
        make = miner_data.make or vnish_device.get("make")
        fw_ver = (
            vnish_device.get("fw_ver")
            if _generic_firmware(miner_data.fw_ver)
            else miner_data.fw_ver or vnish_device.get("fw_ver")
        )

        miner_sensors = {
            "hashrate": normalized_hashrate.value,
            "ideal_hashrate": normalized_expected_hashrate.value,
            "active_preset_name": active_preset,
            "temperature": miner_data.temperature_avg,
            "power_limit": miner_data.wattage_limit,
            "miner_consumption": miner_data.wattage,
            "efficiency": miner_data.efficiency_fract,
        }
        miner_sensors.update(vnish_data.get("miner_sensors", {}))
        for sensor in (
            "instant_hashrate",
            "average_hashrate",
            "nominal_hashrate",
            "stock_hashrate",
        ):
            if sensor in vnish_data.get("miner_sensors", {}):
                sensor_units[sensor] = TERA_HASH_PER_SECOND

        board_sensors = {}
        for board in miner_data.hashboards:
            board_hashrate = normalize_hashrate(board.hashrate)
            if board_hashrate.unit is not None:
                sensor_units["board_hashrate"] = board_hashrate.unit
            board_sensors[board.slot] = {
                "board_temperature": board.temp,
                "chip_temperature": board.chip_temp,
                "board_hashrate": board_hashrate.value or 0,
            }
        for board, sensors in vnish_data.get("board_sensors", {}).items():
            board_sensors.setdefault(board, {}).update(sensors)
            if "board_hashrate" in sensors:
                sensor_units["board_hashrate"] = TERA_HASH_PER_SECOND
            if "board_hashrate_ideal" in sensors:
                sensor_units["board_hashrate_ideal"] = TERA_HASH_PER_SECOND
        if preferred_hashrate_unit is not None:
            sensor_units["board_hashrate"] = preferred_hashrate_unit

        if _uses_vnish_water_cooling(vnish_data):
            fan_sensors = {}
        else:
            fan_sensors = {
                idx: {"fan_speed": fan.speed} for idx, fan in enumerate(miner_data.fans)
            }
            fan_sensors = merge_fan_sensors(
                fan_sensors,
                await fetch_rpc_fan_sensors(self.miner),
            )
            for fan, sensors in vnish_data.get("fan_sensors", {}).items():
                fan_sensors.setdefault(fan, {}).update(sensors)

        data = {
            "hostname": hostname,
            "mac": mac,
            "device_id": device_id,
            "make": make,
            "model": model,
            "ip": miner_ip,
            "is_mining": miner_data.is_mining,
            "fw_ver": fw_ver,
            "miner_sensors": miner_sensors,
            "board_sensors": board_sensors,
            "fan_sensors": fan_sensors,
            "sensor_attributes": vnish_data.get("sensor_attributes", {}),
            "sensor_units": sensor_units,
            "config": miner_data.config,
            "power_limit_range": {
                "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
            },
        }
        return data

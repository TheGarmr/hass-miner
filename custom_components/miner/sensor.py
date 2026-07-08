"""Support for Miner sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import EntityCategory
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.const import REVOLUTIONS_PER_MINUTE
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfTemperature
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .const import JOULES_PER_TERA_HASH
from .const import TERA_HASH_PER_SECOND
from .coordinator import MinerCoordinator
from .entity_helpers import expected_count
from .entity_helpers import miner_device_info
from .voltage_telemetry import normalize_voltage

_LOGGER = logging.getLogger(__name__)

HASHRATE_UNITS = {"KSol/s", TERA_HASH_PER_SECOND}
MINER_HASHRATE_SENSORS = {
    "hashrate",
    "ideal_hashrate",
    "instant_hashrate",
    "average_hashrate",
    "nominal_hashrate",
    "stock_hashrate",
}
BOARD_HASHRATE_SENSORS = {
    "board_hashrate",
    "board_hashrate_ideal",
}


ENTITY_DESCRIPTION_KEY_MAP: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "pcb_temperature_min": SensorEntityDescription(
        key="PCB Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "pcb_temperature_max": SensorEntityDescription(
        key="PCB Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_temperature_min": SensorEntityDescription(
        key="Chip Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_temperature_max": SensorEntityDescription(
        key="Chip Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "water_inlet_temperature_min": SensorEntityDescription(
        key="Water Inlet Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "water_inlet_temperature_max": SensorEntityDescription(
        key="Water Inlet Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "water_outlet_temperature_min": SensorEntityDescription(
        key="Water Outlet Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "water_outlet_temperature_max": SensorEntityDescription(
        key="Water Outlet Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_temperature": SensorEntityDescription(
        key="Board Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_temperature": SensorEntityDescription(
        key="Chip Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "hashrate": SensorEntityDescription(
        key="Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ideal_hashrate": SensorEntityDescription(
        key="Ideal Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "instant_hashrate": SensorEntityDescription(
        key="Instant Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "average_hashrate": SensorEntityDescription(
        key="Average Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "nominal_hashrate": SensorEntityDescription(
        key="Nominal Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "stock_hashrate": SensorEntityDescription(
        key="Stock Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "active_preset_name": SensorEntityDescription(
        key="Active Preset Name",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "current_preset": SensorEntityDescription(
        key="Current Preset",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "mining_time": SensorEntityDescription(
        key="Mining Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "cooling_mode": SensorEntityDescription(
        key="Cooling Mode",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_duty": SensorEntityDescription(
        key="Fan Duty",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "cooling_min_fan_duty": SensorEntityDescription(
        key="Cooling Min Fan Duty",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "cooling_max_fan_duty": SensorEntityDescription(
        key="Cooling Max Fan Duty",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "minimum_startup_water_temperature": SensorEntityDescription(
        key="Minimum Startup Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hashrate": SensorEntityDescription(
        key="Board Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hashrate_ideal": SensorEntityDescription(
        key="Board Ideal Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hashrate_percentage": SensorEntityDescription(
        key="Board Hashrate Percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_frequency": SensorEntityDescription(
        key="Board Frequency",
        native_unit_of_measurement="MHz",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_voltage": SensorEntityDescription(
        key="Board Voltage",
        native_unit_of_measurement="V",
        suggested_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_power": SensorEntityDescription(
        key="Board Power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hw_errors": SensorEntityDescription(
        key="Board HW Errors",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hr_error": SensorEntityDescription(
        key="Board HR Error",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_pcb_temperature_min": SensorEntityDescription(
        key="Board PCB Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_pcb_temperature_max": SensorEntityDescription(
        key="Board PCB Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_chip_temperature_min": SensorEntityDescription(
        key="Board Chip Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_chip_temperature_max": SensorEntityDescription(
        key="Board Chip Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "inlet_water_temperature": SensorEntityDescription(
        key="Inlet Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "outlet_water_temperature": SensorEntityDescription(
        key="Outlet Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "water_temperature_delta": SensorEntityDescription(
        key="Water Temperature Delta",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_status_red": SensorEntityDescription(
        key="Chip Status Red",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_status_orange": SensorEntityDescription(
        key="Chip Status Orange",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_status_grey": SensorEntityDescription(
        key="Chip Status Grey",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "power_limit": SensorEntityDescription(
        key="Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "miner_consumption": SensorEntityDescription(
        key="Miner Consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "efficiency": SensorEntityDescription(
        key="Efficiency",
        native_unit_of_measurement=JOULES_PER_TERA_HASH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "power_efficiency": SensorEntityDescription(
        key="Power Efficiency",
        native_unit_of_measurement=JOULES_PER_TERA_HASH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "hw_errors": SensorEntityDescription(
        key="HW Errors",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "hw_errors_percent": SensorEntityDescription(
        key="HW Errors Percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "devfee_percent": SensorEntityDescription(
        key="Devfee Percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "total_chips": SensorEntityDescription(
        key="Total Chips",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "bad_chips": SensorEntityDescription(
        key="Bad Chips",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_errors": SensorEntityDescription(
        key="Chip Errors",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_detail": SensorEntityDescription(
        key="Chip Detail",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_speed": SensorEntityDescription(
        key="Fan Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_max_speed": SensorEntityDescription(
        key="Fan Max Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_status": SensorEntityDescription(
        key="Fan Status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

MINER_SENSORS_DISABLED_BY_DEFAULT = {
    "active_preset_name",
    "bad_chips",
    "chip_detail",
    "chip_errors",
    "chip_temperature_max",
    "chip_temperature_min",
    "current_preset",
    "devfee_percent",
    "efficiency",
    "hw_errors",
    "hw_errors_percent",
    "nominal_hashrate",
    "pcb_temperature_max",
    "pcb_temperature_min",
    "power_efficiency",
    "stock_hashrate",
    "total_chips",
    "water_inlet_temperature_max",
    "water_inlet_temperature_min",
    "water_outlet_temperature_max",
    "water_outlet_temperature_min",
}

BOARD_SENSORS_DISABLED_BY_DEFAULT = {
    "board_chip_temperature_max",
    "board_chip_temperature_min",
    "board_frequency",
    "board_hashrate_ideal",
    "board_hashrate_percentage",
    "board_hr_error",
    "board_hw_errors",
    "board_pcb_temperature_max",
    "board_pcb_temperature_min",
    "chip_status_grey",
    "chip_status_orange",
    "chip_status_red",
}

FAN_SENSORS_DISABLED_BY_DEFAULT = {"fan_max_speed"}


def _uses_water_cooling(data: dict) -> bool:
    """Return true for miners where cooling is represented as water blocks."""
    mode = str(data.get("miner_sensors", {}).get("cooling_mode", "")).lower()
    if mode in {"immersion", "immers"}:
        return True
    return any(
        "inlet_water_temperature" in board_data
        or "outlet_water_temperature" in board_data
        for board_data in data.get("board_sensors", {}).values()
    )


async def _async_update_hashrate_registry_unit(
    entity_obj: SensorEntity,
    expected_unit: str | None,
) -> None:
    """Update stale hashrate units kept in the entity registry."""
    if expected_unit not in HASHRATE_UNITS or entity_obj.entity_id is None:
        return

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(entity_obj.hass)
    entry = registry.async_get(entity_obj.entity_id)
    if entry is None:
        return

    stale_units = HASHRATE_UNITS - {expected_unit}
    updated_entry = entry
    private_options = dict(entry.options.get("sensor.private", {}))
    if private_options.get("suggested_unit_of_measurement") != expected_unit:
        private_options["suggested_unit_of_measurement"] = expected_unit
        updated_entry = registry.async_update_entity_options(
            entity_obj.entity_id,
            "sensor.private",
            private_options,
        )

    sensor_options = dict(updated_entry.options.get("sensor", {}))
    if sensor_options.get("unit_of_measurement") in stale_units:
        sensor_options.pop("unit_of_measurement", None)
        updated_entry = registry.async_update_entity_options(
            entity_obj.entity_id,
            "sensor",
            sensor_options or None,
        )

    if updated_entry.unit_of_measurement in stale_units:
        updated_entry = registry.async_update_entity(
            entity_obj.entity_id,
            unit_of_measurement=expected_unit,
        )

    entity_obj.registry_entry = updated_entry
    entity_obj._async_read_entity_options()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    def _create_miner_entity(sensor: str) -> MinerSensor:
        """Create a miner sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerSensor(
            coordinator=coordinator,
            sensor=sensor,
            entity_description=description,
        )

    def _create_board_entity(board_num: int, sensor: str) -> MinerBoardSensor:
        """Create a board sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerBoardSensor(
            coordinator=coordinator,
            board_num=board_num,
            sensor=sensor,
            entity_description=description,
        )

    def _create_fan_entity(fan_num: int, sensor: str) -> MinerFanSensor:
        """Create a fan sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerFanSensor(
            coordinator=coordinator,
            fan_num=fan_num,
            sensor=sensor,
            entity_description=description,
        )

    await coordinator.async_config_entry_first_refresh()

    sensors = []
    for s in coordinator.data["miner_sensors"]:
        sensors.append(_create_miner_entity(s))
    board_numbers = sorted(coordinator.data["board_sensors"]) or list(
        range(expected_count(coordinator.miner.expected_hashboards, 3))
    )
    board_sensor_keys = sorted(
        {
            sensor
            for board_data in coordinator.data["board_sensors"].values()
            for sensor in board_data
        }
    ) or ["board_temperature", "chip_temperature", "board_hashrate"]
    for board in board_numbers:
        for s in board_sensor_keys:
            sensors.append(_create_board_entity(board, s))
    fan_numbers = sorted(coordinator.data["fan_sensors"])
    if not fan_numbers and not _uses_water_cooling(coordinator.data):
        fan_numbers = list(range(expected_count(coordinator.miner.expected_fans, 4)))
    fan_sensor_keys = sorted(
        {
            sensor
            for fan_data in coordinator.data["fan_sensors"].values()
            for sensor in fan_data
        }
    ) or ["fan_speed"]
    for fan in fan_numbers:
        for s in fan_sensor_keys:
            sensors.append(_create_fan_entity(fan, s))
    async_add_entities(sensors)


class MinerSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['device_id']}-{sensor}"
        self._sensor = sensor
        self.entity_description = entity_description
        unit = self.coordinator.data.get("sensor_units", {}).get(sensor)
        if sensor in MINER_HASHRATE_SENSORS and unit in HASHRATE_UNITS:
            self._attr_suggested_unit_of_measurement = unit
        if sensor in MINER_SENSORS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Update stale hashrate display options."""
        await super().async_added_to_hass()
        if self._sensor in MINER_HASHRATE_SENSORS:
            await _async_update_hashrate_registry_unit(
                self,
                self.native_unit_of_measurement,
            )

    @property
    def _sensor_data(self):
        """Return sensor data."""
        try:
            return self.coordinator.data["miner_sensors"][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return miner_device_info(
            DOMAIN,
            self.coordinator.data,
            f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit for the current miner algorithm."""
        return self.coordinator.data.get("sensor_units", {}).get(
            self._sensor,
            self.entity_description.native_unit_of_measurement,
        )

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return optional sensor attributes."""
        return self.coordinator.data.get("sensor_attributes", {}).get(self._sensor)

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available


class MinerBoardSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Board Sensor."""

    entity_description: SensorEntityDescription
    _BOARD_VOLTAGE_UNIT = "V"

    def __init__(
        self,
        coordinator: MinerCoordinator,
        board_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['device_id']}-{board_num}-{sensor}"
        self._board_num = board_num
        self._sensor = sensor
        self.entity_description = entity_description
        if sensor == "board_voltage":
            self._attr_suggested_unit_of_measurement = self._BOARD_VOLTAGE_UNIT
        unit = self.coordinator.data.get("sensor_units", {}).get(sensor)
        if sensor in BOARD_HASHRATE_SENSORS and unit in HASHRATE_UNITS:
            self._attr_suggested_unit_of_measurement = unit
        if sensor in BOARD_SENSORS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Update stale board display options."""
        await super().async_added_to_hass()
        if self._sensor in BOARD_HASHRATE_SENSORS:
            await _async_update_hashrate_registry_unit(
                self,
                self.native_unit_of_measurement,
            )

        if self._sensor != "board_voltage" or self.entity_id is None:
            return

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return

        updated_entry = entry
        private_options = dict(entry.options.get("sensor.private", {}))
        if (
            private_options.get("suggested_unit_of_measurement")
            != self._BOARD_VOLTAGE_UNIT
        ):
            private_options["suggested_unit_of_measurement"] = self._BOARD_VOLTAGE_UNIT
            updated_entry = registry.async_update_entity_options(
                self.entity_id,
                "sensor.private",
                private_options,
            )

        sensor_options = dict(updated_entry.options.get("sensor", {}))
        if sensor_options.get("unit_of_measurement") == "mV":
            sensor_options.pop("unit_of_measurement", None)
            updated_entry = registry.async_update_entity_options(
                self.entity_id,
                "sensor",
                sensor_options or None,
            )

        if updated_entry.unit_of_measurement == "mV":
            updated_entry = registry.async_update_entity(
                self.entity_id,
                unit_of_measurement=self._BOARD_VOLTAGE_UNIT,
            )

        self.registry_entry = updated_entry
        self._async_read_entity_options()

    @property
    def _sensor_data(self):
        """Return sensor data."""
        try:
            return self.coordinator.data["board_sensors"][self._board_num][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Board #{self._board_num} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return miner_device_info(
            DOMAIN,
            self.coordinator.data,
            f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if self._sensor == "board_voltage":
            return normalize_voltage(self._sensor_data)
        return self._sensor_data

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit for the current miner algorithm."""
        if self._sensor == "board_voltage":
            return self._BOARD_VOLTAGE_UNIT
        return self.coordinator.data.get("sensor_units", {}).get(
            self._sensor,
            self.entity_description.native_unit_of_measurement,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available


class MinerFanSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Fan Sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        fan_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['device_id']}-{fan_num}-{sensor}"
        self._fan_num = fan_num
        self._sensor = sensor
        self.entity_description = entity_description
        self._attr_force_update = True
        if sensor in FAN_SENSORS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

    @property
    def _sensor_data(self):
        """Return sensor data."""
        try:
            return self.coordinator.data["fan_sensors"][self._fan_num][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Fan #{self._fan_num + 1} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return miner_device_info(
            DOMAIN,
            self.coordinator.data,
            f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available

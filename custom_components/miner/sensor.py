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

_LOGGER = logging.getLogger(__name__)


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
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
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
    "board_voltage",
    "chip_status_grey",
    "chip_status_orange",
    "chip_status_red",
}

FAN_SENSORS_DISABLED_BY_DEFAULT = {"fan_max_speed"}


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
    fan_numbers = sorted(coordinator.data["fan_sensors"]) or list(
        range(expected_count(coordinator.miner.expected_fans, 4))
    )
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
        if sensor in MINER_SENSORS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

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
        if sensor in BOARD_SENSORS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

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
        return self._sensor_data

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit for the current miner algorithm."""
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
        return f"{self.coordinator.config_entry.title} Fan #{self._fan_num} {self.entity_description.key}"

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

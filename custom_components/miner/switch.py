"""Support for Miner shutdown."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity_helpers import miner_device_info
from .miner_control import async_miner_supports_pause
from .miner_control import miner_active_state
from .miner_control import miner_supports_pause
from .miner_control import pause_mining
from .miner_control import resume_mining

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    created = set()

    @callback
    def _create_entity(key: str):
        """Create a sensor entity."""
        created.add(key)

    await coordinator.async_config_entry_first_refresh()
    if await async_miner_supports_pause(coordinator.miner):
        async_add_entities(
            [
                MinerActiveSwitch(
                    coordinator=coordinator,
                )
            ]
        )


class MinerActiveSwitch(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Defines a Miner Switch to pause and unpause the miner."""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['device_id']}-active"
        self._attr_is_on = miner_active_state(
            self.coordinator.miner, self.coordinator.data["is_mining"]
        )
        self.updating_switch = False
        self._last_mining_mode = None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} active"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return miner_device_info(
            DOMAIN,
            self.coordinator.data,
            f"{self.coordinator.config_entry.title}",
        )

    async def async_turn_on(self) -> None:
        """Turn on miner."""
        miner = self.coordinator.miner
        _LOGGER.debug(f"{self.coordinator.config_entry.title}: Resume mining.")
        if not miner_supports_pause(miner) and not await async_miner_supports_pause(
            miner
        ):
            raise TypeError(f"{miner}: Pause switch not supported.")
        result = await resume_mining(miner)
        if not result:
            self._attr_is_on = False
            self.async_write_ha_state()
            import pyasic

            raise pyasic.APIError("Failed to resume mining.")
        self._attr_is_on = True
        if miner.supports_power_modes and self._last_mining_mode:
            try:
                config = await miner.get_config()
                config.mining_mode = self._last_mining_mode
                await miner.send_config(config)
            except Exception as err:
                _LOGGER.warning(f"{self.coordinator.config_entry.title}: Could not restore config: {err}")
        self.updating_switch = True
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off miner."""
        miner = self.coordinator.miner
        _LOGGER.debug(f"{self.coordinator.config_entry.title}: Stop mining.")
        if not miner_supports_pause(miner) and not await async_miner_supports_pause(
            miner
        ):
            raise TypeError(f"{miner}: Pause switch not supported.")
        if miner.supports_power_modes:
            try:
                self._last_mining_mode = self.coordinator.data.get("config", {}).mining_mode if self.coordinator.data.get("config") else None
            except Exception:
                self._last_mining_mode = None
        result = await pause_mining(miner)
        if not result:
            self._attr_is_on = True
            self.async_write_ha_state()
            import pyasic

            raise pyasic.APIError("Failed to pause mining.")
        self._attr_is_on = False
        self.updating_switch = True
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        is_mining = miner_active_state(
            self.coordinator.miner, self.coordinator.data["is_mining"]
        )
        if is_mining is not None:
            if self.updating_switch:
                if is_mining == self._attr_is_on:
                    self.updating_switch = False
            if not self.updating_switch:
                self._attr_is_on = is_mining

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available

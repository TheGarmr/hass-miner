"""Lightweight test for `set_work_mode` device action."""
import asyncio
import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def install_import_stubs():
    """Install minimal Home Assistant stubs for importing device_action."""
    voluptuous = types.ModuleType("voluptuous")
    voluptuous.Required = lambda key, *args, **kwargs: key
    voluptuous.Optional = lambda key, *args, **kwargs: key
    voluptuous.In = lambda values: values
    sys.modules.setdefault("voluptuous", voluptuous)

    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components)

    miner_package = types.ModuleType("custom_components.miner")
    miner_package.__path__ = [str(ROOT / "custom_components" / "miner")]
    sys.modules.setdefault("custom_components.miner", miner_package)

    homeassistant = types.ModuleType("homeassistant")
    sys.modules.setdefault("homeassistant", homeassistant)

    const = types.ModuleType("homeassistant.const")
    const.CONF_DEVICE_ID = "device_id"
    const.CONF_DOMAIN = "domain"
    const.CONF_TYPE = "type"
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")
    core.Context = object
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    sys.modules["homeassistant.components"] = components

    device_automation = types.ModuleType("homeassistant.components.device_automation")

    async def async_validate_entity_schema(hass, config, schema):
        return config

    device_automation.async_validate_entity_schema = async_validate_entity_schema
    sys.modules["homeassistant.components.device_automation"] = device_automation

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    config_validation = types.ModuleType("homeassistant.helpers.config_validation")

    class BaseSchema:
        def extend(self, schema):
            return schema

    config_validation.DEVICE_ACTION_BASE_SCHEMA = BaseSchema()
    sys.modules["homeassistant.helpers.config_validation"] = config_validation

    helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict
    sys.modules["homeassistant.helpers.typing"] = helpers_typing


def load_async_call_action_from_config():
    """Load the target function without importing Home Assistant."""
    install_import_stubs()
    module = importlib.import_module("custom_components.miner.device_action")
    return module.async_call_action_from_config


class FakeServices:
    """Fake Home Assistant services registry capturing service calls."""

    def __init__(self):
        """Initialize the fake services store."""
        self.calls = []

    async def async_call(
        self, domain, service, service_data, blocking=True, context=None
    ):
        """Record an async service call with its parameters."""
        self.calls.append(
            {
                "domain": domain,
                "service": service,
                "service_data": service_data,
                "blocking": blocking,
                "context": context,
            }
        )


class FakeHass:
    """Fake Home Assistant core object exposing `services`."""

    def __init__(self):
        """Initialize the fake hass container with services."""
        self.services = FakeServices()


async def main():
    """Run a simple assertion flow to validate service call building."""
    async_call_action_from_config = load_async_call_action_from_config()
    hass = FakeHass()
    config = {
        "type": "set_work_mode",
        "domain": "miner",
        "device_id": "device-123",
        "mode": "normal",
    }
    variables = {}
    context = None

    await async_call_action_from_config(hass, config, variables, context)

    assert len(hass.services.calls) == 1, "Expected one service call"
    call = hass.services.calls[0]
    assert call["domain"] == "miner"
    assert call["service"] == "set_work_mode"
    assert call["service_data"]["device_id"] == ["device-123"]
    assert call["service_data"]["mode"] == "normal"


if __name__ == "__main__":
    asyncio.run(main())

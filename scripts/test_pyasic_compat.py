"""Lightweight tests for fork-local pyasic compatibility patches."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pyasic
from pyasic.miners.factory import MINER_CLASSES
from pyasic.miners.factory import MinerFactory
from pyasic.miners.factory import MinerTypes


def load_module():
    """Load pyasic_compat without importing Home Assistant package modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "pyasic_compat.py"
    spec = importlib.util.spec_from_file_location("miner_pyasic_compat", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    """Run compatibility assertions."""
    compat = load_module()
    antminer_classes = MINER_CLASSES[MinerTypes.ANTMINER]

    antminer_classes.pop("ANTMINER Z11", None)
    antminer_classes.pop("ANTMINER S21+ HYDRO", None)
    antminer_classes.pop("ANTMINER S21 PLUS HYDRO", None)
    if hasattr(pyasic, "_hass_miner_compat_applied"):
        delattr(pyasic, "_hass_miner_compat_applied")

    compat.apply_pyasic_compat(pyasic)

    z11_cls = antminer_classes["ANTMINER Z11"]
    assert z11_cls.__name__ == "CGMinerZ11"
    z11_miner = z11_cls("192.0.2.10")
    assert z11_miner.model == "Z11"
    assert z11_miner.device_info.model is None
    assert z11_cls.expected_hashboards == 3
    assert z11_cls.expected_chips == 9
    assert z11_cls.expected_fans == 2
    assert str(z11_cls.algo) == str(compat.MinerAlgo.EQUIHASH)

    assert antminer_classes["ANTMINER S21+ HYDRO"] is antminer_classes[
        "ANTMINER S21+ HYD."
    ]
    assert antminer_classes["ANTMINER S21 PLUS HYDRO"] is antminer_classes[
        "ANTMINER S21+ HYD."
    ]

    before = dict(antminer_classes)
    patched_model_fn = MinerFactory.get_miner_model_antminer
    compat.apply_pyasic_compat(pyasic)
    assert antminer_classes == before
    delattr(pyasic, "_hass_miner_compat_applied")
    compat.apply_pyasic_compat(pyasic)
    assert MinerFactory.get_miner_model_antminer is patched_model_fn

    check_blank_antminer_model_fallback()


def check_blank_antminer_model_fallback():
    """Blank Antminer type falls back to the model named in CompileTime."""
    factory = MinerFactory()
    version_reply = {
        "VERSION": [
            {
                "CompileTime": "Uspex Z15 Custom Firmware 2026 v29 FINAL",
                "Type": "",
            }
        ]
    }

    async def fake_web(ip):
        return ""

    async def fake_sock(ip):
        return ""

    async def fake_api(ip, command):
        assert command == "version"
        return version_reply

    factory._get_model_antminer_web = fake_web
    factory._get_model_antminer_sock = fake_sock
    factory.send_api_command = fake_api

    assert asyncio.run(factory.get_miner_model_antminer("192.0.2.36")) == "Antminer Z15"

    version_reply["VERSION"][0]["CompileTime"] = "Fri Jul  3 11:39:06 CST 2020"
    assert asyncio.run(factory.get_miner_model_antminer("192.0.2.36")) == ""


if __name__ == "__main__":
    main()

"""Fork-local compatibility patches for pyasic miner detection."""
from __future__ import annotations

import logging
import re
from typing import Any

from pyasic.device.algorithm import MinerAlgo

_LOGGER = logging.getLogger(__name__)
_PATCH_MARKER = "_hass_miner_compat_applied"


def apply_pyasic_compat(pyasic_module: Any) -> None:
    """Apply idempotent runtime patches to pyasic factory mappings."""
    if getattr(pyasic_module, _PATCH_MARKER, False):
        return

    try:
        from pyasic.miners.backends.antminer import AntminerOld
        from pyasic.miners.device.makes import AntMinerMake
        from pyasic.miners.factory import MINER_CLASSES
        from pyasic.miners.factory import MinerTypes
    except Exception as err:
        _LOGGER.warning("Unable to import pyasic compatibility targets: %s", err)
        return

    class Z11(AntMinerMake):
        """Antminer Z11 model metadata for local pyasic compatibility."""

        raw_model = None
        expected_chips = 9
        expected_hashboards = 3
        expected_fans = 2
        algo = MinerAlgo.EQUIHASH

        @property
        def model(self) -> str:
            """Return a display model without violating pyasic model typing."""
            return "Z11"

    class CGMinerZ11(AntminerOld, Z11):
        """Antminer Z11 handler using the old Antminer CGMiner backend."""

        supports_shutdown = False

    antminer_classes = MINER_CLASSES[MinerTypes.ANTMINER]
    antminer_classes.setdefault("ANTMINER Z11", CGMinerZ11)

    s21_plus_hydro = antminer_classes.get("ANTMINER S21+ HYD.") or antminer_classes.get(
        "ANTMINER S21+ HYD"
    )
    if s21_plus_hydro is not None:
        antminer_classes.setdefault("ANTMINER S21+ HYDRO", s21_plus_hydro)
        antminer_classes.setdefault("ANTMINER S21 PLUS HYDRO", s21_plus_hydro)

    _patch_blank_antminer_model()

    setattr(pyasic_module, _PATCH_MARKER, True)


# Custom Z-series firmwares (e.g. "Uspex Z15 Custom Firmware") report an empty
# "Type"/"minertype", so pyasic falls back to AntminerUnknown and returns no
# boards, fans or MAC. The model name is still present in CompileTime.
_ANTMINER_MODEL_IN_TEXT = re.compile(r"\b(Z1[15])\b", re.IGNORECASE)


def _patch_blank_antminer_model() -> None:
    """Infer the Antminer model from firmware text when the type is blank."""
    from pyasic.miners.factory import MinerFactory

    original = MinerFactory.get_miner_model_antminer
    if getattr(original, _PATCH_MARKER, False):
        return

    async def get_miner_model_antminer(self, ip: str) -> str | None:
        model = await original(self, ip)
        if model:
            return model

        try:
            data = await self.send_api_command(ip, "version")
            compile_time = data["VERSION"][0]["CompileTime"]
        except (TypeError, LookupError):
            return model

        match = _ANTMINER_MODEL_IN_TEXT.search(str(compile_time))
        if match is None:
            return model

        inferred = f"Antminer {match.group(1).upper()}"
        _LOGGER.debug("%s: blank Antminer type, inferred %s from firmware", ip, inferred)
        return inferred

    setattr(get_miner_model_antminer, _PATCH_MARKER, True)
    MinerFactory.get_miner_model_antminer = get_miner_model_antminer

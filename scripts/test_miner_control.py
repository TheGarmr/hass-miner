"""Lightweight tests for miner pause/resume control helpers."""
# ruff: noqa: D102,D107
from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path


def load_module():
    """Load miner_control without importing Home Assistant package modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "miner_control.py"
    spec = importlib.util.spec_from_file_location("miner_control", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ModernMiner:
    """Fake miner using the default pyasic pause path."""

    supports_shutdown = True
    model = "S21+ Hydro"

    def __init__(self):
        self.calls = []

    async def stop_mining(self):
        self.calls.append("stop")
        return True

    async def resume_mining(self):
        self.calls.append("resume")
        return True


class EmptyResponseMiner:
    """Fake VNish miner that applies command but returns an empty response."""

    supports_shutdown = True
    model = "S21+ Hydro"

    def __init__(self, states):
        self.states = list(states)
        self.calls = []

    async def stop_mining(self):
        self.calls.append("stop")
        raise RuntimeError(
            "JSON decode error for 'mining/stop': Response: empty response"
        )

    async def resume_mining(self):
        self.calls.append("resume")
        raise RuntimeError(
            "JSON decode error for 'mining/start': Response: empty response"
        )

    async def is_mining(self):
        if self.states:
            return self.states.pop(0)
        return None


class BrokenModernMiner:
    """Fake modern miner with a real command failure."""

    supports_shutdown = True
    model = "S21+ Hydro"

    async def stop_mining(self):
        raise RuntimeError("connection failed")


class FakeWeb:
    """Fake old Antminer web API."""

    def __init__(
        self,
        *,
        pools=None,
        set_error=None,
        apply_payload=True,
        apply_on_error=False,
    ):
        self.payloads = []
        self.set_error = set_error
        self.apply_payload = apply_payload
        self.apply_on_error = apply_on_error
        self.conf = {
            "pools": pools
            or [
                {"url": "stratum+tcp://pool1", "user": "worker1", "pass": "x"},
                {"url": "stratum+tcp://pool2", "user": "worker2", "pass": "y"},
                {"url": "", "user": "", "pass": ""},
            ],
            "api-listen": True,
            "api-network": True,
            "api-groups": "A:stats:pools:devs:summary:version",
            "api-allow": "A:0/0,W:*",
            "bitmain-use-vil": True,
            "bitmain-freq": "718",
            "bitmain-fan-ctrl": False,
            "bitmain-fan-pwm": "100",
        }

    async def get_miner_conf(self):
        return self.conf

    async def set_miner_conf(self, payload):
        self.payloads.append(payload)
        if self.apply_payload and (self.set_error is None or self.apply_on_error):
            for idx in range(3):
                slot = idx + 1
                self.conf["pools"][idx]["url"] = payload[f"_ant_pool{slot}url"]
                self.conf["pools"][idx]["user"] = payload[f"_ant_pool{slot}user"]
                self.conf["pools"][idx]["pass"] = payload[f"_ant_pool{slot}pw"]
            for key, value in payload.items():
                if not key.startswith("_ant_pool"):
                    self.conf[key] = value
        if self.set_error is not None:
            raise self.set_error
        return {"success": True}


class OldAntminer:
    """Fake Z15/Z11 style miner using web-config fallback."""

    supports_shutdown = False

    def __init__(
        self,
        states,
        model="Z15",
        *,
        pools=None,
        set_error=None,
        apply_payload=True,
        apply_on_error=False,
    ):
        self.web = FakeWeb(
            pools=pools,
            set_error=set_error,
            apply_payload=apply_payload,
            apply_on_error=apply_on_error,
        )
        self.states = list(states)
        self.model = model
        self.raw_model = model

    async def is_mining(self):
        if self.states:
            return self.states.pop(0)
        return None


async def main():
    """Run control assertions."""
    control = load_module()
    control._OLD_ANTMINER_CONFIRM_ATTEMPTS = 1
    control._OLD_ANTMINER_CONFIRM_DELAY = 0
    logging.disable(logging.WARNING)

    modern = ModernMiner()
    assert control.miner_supports_pause(modern)
    assert await control.pause_mining(modern)
    assert await control.resume_mining(modern)
    assert modern.calls == ["stop", "resume"]

    empty_pause = EmptyResponseMiner(states=[False])
    assert await control.pause_mining(empty_pause, confirm_attempts=1, confirm_delay=0)
    assert empty_pause.calls == ["stop"]

    empty_resume = EmptyResponseMiner(states=[True])
    assert await control.resume_mining(empty_resume, confirm_attempts=1, confirm_delay=0)
    assert empty_resume.calls == ["resume"]

    failed_empty = EmptyResponseMiner(states=[True])
    assert not await control.pause_mining(
        failed_empty, confirm_attempts=1, confirm_delay=0
    )

    broken = BrokenModernMiner()
    try:
        await control.pause_mining(broken, confirm_attempts=1, confirm_delay=0)
    except RuntimeError as err:
        assert str(err) == "connection failed"
    else:
        raise AssertionError("expected non-empty-response failures to propagate")

    marker = control._OLD_ANTMINER_POOL_MARKER

    old = OldAntminer(states=[False])
    assert not control.miner_supports_pause(old)
    assert await control.async_miner_supports_pause(old)
    assert control.miner_supports_pause(old)
    assert control.miner_active_state(old, True) is True
    assert await control.pause_mining(old, confirm_attempts=1, confirm_delay=0)
    assert old.web.payloads == [
        {
            "_ant_pool1url": f"{marker}stratum+tcp://pool1",
            "_ant_pool1user": "worker1",
            "_ant_pool1pw": "x",
            "_ant_pool2url": f"{marker}stratum+tcp://pool2",
            "_ant_pool2user": "worker2",
            "_ant_pool2pw": "y",
            "_ant_pool3url": "",
            "_ant_pool3user": "",
            "_ant_pool3pw": "",
            "api-listen": True,
            "api-network": True,
            "api-groups": "A:stats:pools:devs:summary:version",
            "api-allow": "A:0/0,W:*",
            "bitmain-use-vil": True,
            "bitmain-freq": "718",
            "bitmain-fan-ctrl": False,
            "bitmain-fan-pwm": "100",
        }
    ]
    assert control.miner_active_state(old, True) is False

    already_paused = OldAntminer(
        states=[False],
        pools=[
            {"url": f"{marker}stratum+tcp://pool1", "user": "worker1", "pass": "x"},
            {"url": f"{marker}stratum+tcp://pool2", "user": "worker2", "pass": "y"},
            {"url": "", "user": "", "pass": ""},
        ],
    )
    assert await control.async_miner_supports_pause(already_paused)
    assert control.miner_active_state(already_paused, True) is False
    assert await control.pause_mining(
        already_paused, confirm_attempts=1, confirm_delay=0
    )
    assert already_paused.web.payloads == []

    z11 = OldAntminer(states=[False], model="Z11")
    assert await control.async_miner_supports_pause(z11)
    assert control.miner_supports_pause(z11)
    assert await control.pause_mining(z11, confirm_attempts=1, confirm_delay=0)
    z11_payload = z11.web.payloads[0]
    assert z11_payload["_ant_pool1url"] == f"{marker}stratum+tcp://pool1"
    assert z11_payload["_ant_pool1user"] == "worker1"
    assert z11_payload["_ant_pool1pw"] == "x"
    assert z11_payload["_ant_pool2url"] == f"{marker}stratum+tcp://pool2"
    assert z11_payload["_ant_pool2user"] == "worker2"
    assert z11_payload["_ant_pool2pw"] == "y"
    assert z11_payload["bitmain-fan-ctrl"] is False
    assert z11_payload["bitmain-fan-pwm"] == "100"

    three_pool_miner = OldAntminer(
        states=[False],
        pools=[
            {"url": "stratum+tcp://pool1", "user": "worker1", "pass": "x"},
            {"url": "stratum+tcp://pool2", "user": "worker2", "pass": "y"},
            {"url": "stratum+tcp://pool3", "user": "worker3", "pass": "z"},
        ],
    )
    assert await control.async_miner_supports_pause(three_pool_miner)
    assert await control.pause_mining(
        three_pool_miner, confirm_attempts=1, confirm_delay=0
    )
    three_pool_pause_payload = three_pool_miner.web.payloads[0]
    assert three_pool_pause_payload["_ant_pool1url"] == f"{marker}stratum+tcp://pool1"
    assert three_pool_pause_payload["_ant_pool2url"] == f"{marker}stratum+tcp://pool2"
    assert three_pool_pause_payload["_ant_pool3url"] == f"{marker}stratum+tcp://pool3"
    assert three_pool_pause_payload["_ant_pool3user"] == "worker3"
    assert three_pool_pause_payload["_ant_pool3pw"] == "z"

    assert await control.resume_mining(
        three_pool_miner, confirm_attempts=1, confirm_delay=0
    )
    three_pool_resume_payload = three_pool_miner.web.payloads[1]
    assert three_pool_resume_payload["_ant_pool1url"] == "stratum+tcp://pool1"
    assert three_pool_resume_payload["_ant_pool2url"] == "stratum+tcp://pool2"
    assert three_pool_resume_payload["_ant_pool3url"] == "stratum+tcp://pool3"
    assert three_pool_resume_payload["_ant_pool3user"] == "worker3"
    assert three_pool_resume_payload["_ant_pool3pw"] == "z"

    ambiguous = OldAntminer(
        states=[True],
        pools=[
            {"url": f"{marker}stratum+tcp://pool1", "user": "worker1", "pass": "x"},
            {"url": f"{marker}stratum+tcp://pool2", "user": "worker2", "pass": "y"},
            {"url": "", "user": "", "pass": ""},
        ],
        set_error=RuntimeError("Failed to send command to miner: AntminerOldWebAPI"),
        apply_on_error=True,
    )
    assert await control.resume_mining(ambiguous, confirm_attempts=1, confirm_delay=0)
    assert ambiguous.web.payloads[0]["_ant_pool1url"] == "stratum+tcp://pool1"
    assert ambiguous.web.payloads[0]["_ant_pool2url"] == "stratum+tcp://pool2"
    assert control.miner_active_state(ambiguous, False) is True

    failed_command = OldAntminer(
        states=[False],
        set_error=RuntimeError("auth failed"),
    )
    assert not await control.pause_mining(
        failed_command, confirm_attempts=1, confirm_delay=0
    )

    old_resume = OldAntminer(
        states=[True],
        pools=[
            {"url": f"{marker}stratum+tcp://pool1", "user": "worker1", "pass": "x"},
            {"url": f"{marker}stratum+tcp://pool2", "user": "worker2", "pass": "y"},
            {"url": "", "user": "", "pass": ""},
        ],
    )
    assert await control.async_miner_supports_pause(old_resume)
    assert await control.resume_mining(old_resume, confirm_attempts=1, confirm_delay=0)
    assert old_resume.web.payloads[0]["_ant_pool1url"] == "stratum+tcp://pool1"
    assert old_resume.web.payloads[0]["_ant_pool1user"] == "worker1"
    assert old_resume.web.payloads[0]["_ant_pool1pw"] == "x"
    assert old_resume.web.payloads[0]["_ant_pool2url"] == "stratum+tcp://pool2"
    assert old_resume.web.payloads[0]["_ant_pool2user"] == "worker2"
    assert old_resume.web.payloads[0]["_ant_pool2pw"] == "y"

    already_resumed = OldAntminer(states=[True])
    assert await control.async_miner_supports_pause(already_resumed)
    assert await control.resume_mining(
        already_resumed, confirm_attempts=1, confirm_delay=0
    )
    assert already_resumed.web.payloads == []

    rejected = OldAntminer(states=[True], apply_payload=False)
    assert await control.async_miner_supports_pause(rejected)
    assert not await control.pause_mining(
        rejected, confirm_attempts=1, confirm_delay=0
    )
    assert rejected.web.payloads[0]["_ant_pool1url"] == f"{marker}stratum+tcp://pool1"

    unsupported = object()
    assert not control.miner_supports_pause(unsupported)
    assert not await control.async_miner_supports_pause(unsupported)
    assert not await control.pause_mining(unsupported, confirm_attempts=1, confirm_delay=0)
    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    asyncio.run(main())

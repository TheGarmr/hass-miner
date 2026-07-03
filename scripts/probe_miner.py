"""Probe a real miner through pyasic with hass-miner compatibility patches."""
# ruff: noqa: T201
from __future__ import annotations

# Example:
#   $env:MINER_WEB_USERNAME="root"
#   $env:MINER_WEB_PASSWORD="root"
#   python scripts\probe_miner.py 192.168.1.50
#   python scripts\probe_miner.py 192.168.1.50 --pause-test

import argparse
import asyncio
import importlib.util
import os
from pathlib import Path

import pyasic


def load_module(name: str, filename: str):
    """Load a helper module without importing Home Assistant package modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async def main():
    """Run a real-device probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("ip")
    parser.add_argument("--pause-test", action="store_true")
    args = parser.parse_args()

    compat = load_module("miner_pyasic_compat", "pyasic_compat.py")
    control = load_module("miner_control", "miner_control.py")
    compat.apply_pyasic_compat(pyasic)

    miner = await pyasic.get_miner(args.ip)
    if miner is None:
        print("miner=None")
        return

    if miner.web is not None:
        miner.web.username = os.environ.get(
            "MINER_WEB_USERNAME", getattr(miner.web, "username", "root")
        )
        miner.web.pwd = os.environ.get(
            "MINER_WEB_PASSWORD", getattr(miner.web, "pwd", "root")
        )
    if miner.api is not None and getattr(miner.api, "pwd", None) is not None:
        miner.api.pwd = os.environ.get("MINER_RPC_PASSWORD", miner.api.pwd)
    if miner.ssh is not None:
        miner.ssh.username = os.environ.get(
            "MINER_SSH_USERNAME", getattr(miner.ssh, "username", "miner")
        )
        miner.ssh.pwd = os.environ.get(
            "MINER_SSH_PASSWORD", getattr(miner.ssh, "pwd", "root")
        )

    data = await miner.get_data()
    print(f"class={miner.__class__.__name__}")
    print(f"make={data.make}")
    print(f"model={data.model}")
    print(f"miner_model={miner.model}")
    print(f"firmware={data.fw_ver}")
    print(f"mac={data.mac}")
    print(f"supports_shutdown={getattr(miner, 'supports_shutdown', None)}")
    print(f"supports_pause={control.miner_supports_pause(miner)}")
    print(f"is_mining={data.is_mining}")

    if args.pause_test:
        paused = await control.pause_mining(miner)
        print(f"pause_result={paused}")
        resumed = await control.resume_mining(miner)
        print(f"resume_result={resumed}")


if __name__ == "__main__":
    asyncio.run(main())

"""Lightweight tests for runtime dependency recovery helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    """Load runtime_dependencies without importing Home Assistant modules."""
    root = Path(__file__).resolve().parents[1]
    module_path = root / "custom_components" / "miner" / "runtime_dependencies.py"
    spec = importlib.util.spec_from_file_location(
        "miner_runtime_dependencies", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    """Run runtime dependency assertions."""
    runtime_dependencies = load_module()

    fake_modules = {
        "asyncssh": object(),
        "asyncssh.compression": object(),
        "pyasic": object(),
        "pyasic.device": object(),
        "pyasic_extra": object(),
    }
    previous_modules = {
        name: sys.modules.get(name) for name in fake_modules
    }
    sys.modules.update(fake_modules)

    try:
        runtime_dependencies.clear_cached_runtime_modules()
        assert "asyncssh" not in sys.modules
        assert "asyncssh.compression" not in sys.modules
        assert "pyasic" not in sys.modules
        assert "pyasic.device" not in sys.modules
        assert sys.modules["pyasic_extra"] is fake_modules["pyasic_extra"]
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module

    imported = []
    original_import_module = runtime_dependencies.import_module
    runtime_dependencies.import_module = imported.append
    try:
        runtime_dependencies.validate_asyncssh()
    finally:
        runtime_dependencies.import_module = original_import_module
    assert imported == ["asyncssh.compression"]


if __name__ == "__main__":
    main()

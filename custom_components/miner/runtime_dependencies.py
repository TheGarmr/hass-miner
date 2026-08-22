"""Runtime dependency checks for packages installed outside HA constraints."""
from __future__ import annotations

import sys
from importlib import import_module

_RUNTIME_PACKAGE_ROOTS = ("asyncssh", "pyasic")


def validate_asyncssh() -> None:
    """Raise ImportError when the AsyncSSH installation is incomplete."""
    import_module("asyncssh.compression")


def clear_cached_runtime_modules() -> None:
    """Remove partial dependency imports before or after package repair."""
    for module_name in tuple(sys.modules):
        if any(
            module_name == package_name
            or module_name.startswith(f"{package_name}.")
            for package_name in _RUNTIME_PACKAGE_ROOTS
        ):
            sys.modules.pop(module_name, None)

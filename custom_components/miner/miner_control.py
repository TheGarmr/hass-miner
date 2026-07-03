"""Pause/resume control helpers for miner devices."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)
_OLD_ANTMINER_PAUSE_MODELS = ("Z11", "Z15")
_OLD_ANTMINER_POOL_MARKER = "hass-miner-paused+"
_OLD_ANTMINER_PAUSE_SUPPORTED_ATTR = "_hass_miner_old_antminer_pause_supported"
_OLD_ANTMINER_POOL_PAUSED_ATTR = "_hass_miner_old_antminer_pool_paused"
_OLD_ANTMINER_CONFIRM_ATTEMPTS = 12
_OLD_ANTMINER_CONFIRM_DELAY = 5.0


def _model_text(miner: Any) -> str:
    """Return uppercase model text for allow-list checks."""
    values = [
        getattr(miner, "model", None),
        getattr(miner, "raw_model", None),
    ]
    return " ".join(str(value) for value in values if value).upper()


def _supports_old_antminer_pause_candidate(miner: Any) -> bool:
    """Return whether miner is an allow-listed old Antminer pause candidate."""
    if getattr(miner, "supports_shutdown", False):
        return False
    if not any(model in _model_text(miner) for model in _OLD_ANTMINER_PAUSE_MODELS):
        return False
    web = getattr(miner, "web", None)
    return (
        callable(getattr(web, "get_miner_conf", None))
        and callable(getattr(web, "set_miner_conf", None))
        and callable(getattr(miner, "is_mining", None))
    )


def miner_supports_pause(miner: Any) -> bool:
    """Return whether this integration can expose a pause switch for miner."""
    return bool(getattr(miner, "supports_shutdown", False)) or (
        _supports_old_antminer_pause_candidate(miner)
        and bool(getattr(miner, _OLD_ANTMINER_PAUSE_SUPPORTED_ATTR, False))
    )


def miner_active_state(miner: Any, is_mining: bool | None) -> bool | None:
    """Return switch state, using pool markers for old Antminer pause fallback."""
    if _supports_old_antminer_pause_candidate(miner):
        pool_paused = getattr(miner, _OLD_ANTMINER_POOL_PAUSED_ATTR, None)
        if pool_paused is not None:
            return not bool(pool_paused)
    return is_mining


async def async_miner_supports_pause(miner: Any) -> bool:
    """Return whether miner supports pause, probing old Antminer config if needed."""
    if getattr(miner, "supports_shutdown", False):
        return True
    if not _supports_old_antminer_pause_candidate(miner):
        return False
    setattr(miner, _OLD_ANTMINER_PAUSE_SUPPORTED_ATTR, True)
    await _refresh_old_antminer_pool_pause_state(miner)
    return True


async def pause_mining(
    miner: Any, *, confirm_attempts: int = 3, confirm_delay: float = 2.0
) -> bool:
    """Pause mining and return whether the command was accepted or confirmed."""
    if getattr(miner, "supports_shutdown", False):
        return await _run_shutdown_command(
            miner,
            command=miner.stop_mining,
            expected_is_mining=False,
            confirm_attempts=confirm_attempts,
            confirm_delay=confirm_delay,
        )
    if _supports_old_antminer_pause_candidate(miner):
        return await _set_old_antminer_pool_pause(
            miner,
            paused=True,
            confirm_attempts=confirm_attempts,
            confirm_delay=confirm_delay,
        )
    return False


async def resume_mining(
    miner: Any, *, confirm_attempts: int = 3, confirm_delay: float = 2.0
) -> bool:
    """Resume mining and return whether the command was accepted or confirmed."""
    if getattr(miner, "supports_shutdown", False):
        return await _run_shutdown_command(
            miner,
            command=miner.resume_mining,
            expected_is_mining=True,
            confirm_attempts=confirm_attempts,
            confirm_delay=confirm_delay,
        )
    if _supports_old_antminer_pause_candidate(miner):
        return await _set_old_antminer_pool_pause(
            miner,
            paused=False,
            confirm_attempts=confirm_attempts,
            confirm_delay=confirm_delay,
        )
    return False


async def _run_shutdown_command(
    miner: Any,
    *,
    command: Any,
    expected_is_mining: bool,
    confirm_attempts: int,
    confirm_delay: float,
) -> bool:
    """Run a modern shutdown command, confirming empty-response successes."""
    try:
        return bool(await command())
    except Exception as err:
        if not _is_empty_response_error(err):
            raise
        _LOGGER.debug(
            "%s: shutdown command returned an empty response, confirming state: %s",
            miner,
            err,
        )
        return await _confirm_mining_state(
            miner,
            expected_is_mining=expected_is_mining,
            attempts=confirm_attempts,
            delay=confirm_delay,
        )


def _is_empty_response_error(err: Exception) -> bool:
    """Return whether pyasic failed only because the miner returned no JSON."""
    text = str(err).lower()
    return "json decode" in text and "empty response" in text


async def _set_old_antminer_pool_pause(
    miner: Any,
    *,
    paused: bool,
    confirm_attempts: int,
    confirm_delay: float,
) -> bool:
    """Pause old Antminer by making pool URLs invalid and verify config state."""
    try:
        conf = await miner.web.get_miner_conf()
        setattr(miner, _OLD_ANTMINER_PAUSE_SUPPORTED_ATTR, True)
        current_state = _old_antminer_pool_pause_state(conf)
        if current_state is paused:
            setattr(miner, _OLD_ANTMINER_POOL_PAUSED_ATTR, paused)
            return True
        payload = _old_antminer_pool_pause_payload(conf, paused=paused)
    except Exception as err:
        _LOGGER.warning("%s: old Antminer pool pause payload failed: %s", miner, err)
        return False

    response: Any = None
    try:
        response = await miner.web.set_miner_conf(payload)
    except Exception as err:
        if not _is_old_antminer_ambiguous_set_conf_error(err):
            _LOGGER.warning("%s: old Antminer pool pause command failed: %s", miner, err)
            return False
        response = err
        _LOGGER.debug(
            "%s: old Antminer pool pause command returned an ambiguous response, "
            "confirming state: %s",
            miner,
            err,
        )

    confirmed = await _confirm_old_antminer_pool_pause_state(
        miner,
        expected_paused=paused,
        attempts=max(confirm_attempts, _OLD_ANTMINER_CONFIRM_ATTEMPTS),
        delay=max(confirm_delay, _OLD_ANTMINER_CONFIRM_DELAY),
    )
    if not confirmed:
        _LOGGER.warning(
            "%s: old Antminer pool pause response did not confirm state change: %s",
            miner,
            response,
        )
    return confirmed


def _is_old_antminer_ambiguous_set_conf_error(err: Exception) -> bool:
    """Return whether old Antminer may have applied config despite the error."""
    text = str(err).lower()
    return "failed to send command to miner" in text


async def _refresh_old_antminer_pool_pause_state(miner: Any) -> bool | None:
    """Refresh cached pool pause state for old Antminer fallback."""
    try:
        conf = await miner.web.get_miner_conf()
    except Exception as err:
        _LOGGER.debug("%s: old Antminer pool pause state probe failed: %s", miner, err)
        return None
    state = _old_antminer_pool_pause_state(conf)
    if state is not None:
        setattr(miner, _OLD_ANTMINER_POOL_PAUSED_ATTR, state)
    return state


async def _confirm_old_antminer_pool_pause_state(
    miner: Any, *, expected_paused: bool, attempts: int, delay: float
) -> bool:
    """Poll miner config until pool URLs match the requested pause state."""
    for attempt in range(attempts):
        state = await _refresh_old_antminer_pool_pause_state(miner)
        if state is expected_paused:
            return True
        if attempt < attempts - 1 and delay > 0:
            await asyncio.sleep(delay)
    return False


def _old_antminer_pool_pause_state(conf: dict[str, Any]) -> bool | None:
    """Return pause state encoded in old Antminer pool URLs."""
    urls = _old_antminer_pool_urls(conf)
    if not urls:
        return None
    marked = [url.startswith(_OLD_ANTMINER_POOL_MARKER) for url in urls]
    if all(marked):
        return True
    if not any(marked):
        return False
    return None


def _old_antminer_pool_urls(conf: dict[str, Any]) -> list[str]:
    """Return non-empty old Antminer pool URLs from config."""
    pools = conf.get("pools")
    if not isinstance(pools, list):
        return []
    urls: list[str] = []
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        url = pool.get("url")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def _old_antminer_pool_pause_payload(
    conf: dict[str, Any], *, paused: bool
) -> dict[str, Any]:
    """Build an old Antminer config payload with reversible pool URL markers."""
    payload: dict[str, Any] = {}
    pools = conf.get("pools")
    if isinstance(pools, list):
        for idx in range(3):
            pool = pools[idx] if idx < len(pools) and isinstance(pools[idx], dict) else {}
            slot = idx + 1
            payload[f"_ant_pool{slot}url"] = _old_antminer_pool_url_for_state(
                pool.get("url", ""), paused=paused
            )
            payload[f"_ant_pool{slot}user"] = pool.get("user", "")
            payload[f"_ant_pool{slot}pw"] = pool.get("pass", "")

    for key in (
        "api-listen",
        "api-network",
        "api-groups",
        "api-allow",
        "bitmain-use-vil",
        "bitmain-freq",
        "bitmain-fan-ctrl",
        "bitmain-fan-pwm",
        "bitmain-fan-pwn",
    ):
        if key in conf:
            payload[key] = conf[key]

    return payload


def _old_antminer_pool_url_for_state(url: Any, *, paused: bool) -> str:
    """Return pool URL transformed for the requested pause state."""
    if not isinstance(url, str) or not url:
        return ""
    if paused:
        if url.startswith(_OLD_ANTMINER_POOL_MARKER):
            return url
        return f"{_OLD_ANTMINER_POOL_MARKER}{url}"
    while url.startswith(_OLD_ANTMINER_POOL_MARKER):
        url = url[len(_OLD_ANTMINER_POOL_MARKER) :]
    return url


async def _confirm_mining_state(
    miner: Any, *, expected_is_mining: bool, attempts: int, delay: float
) -> bool:
    """Poll miner.is_mining until the expected state is observed."""
    for attempt in range(attempts):
        try:
            state = await miner.is_mining()
        except Exception as err:
            _LOGGER.debug("%s: is_mining check failed: %s", miner, err)
            state = None
        if state is expected_is_mining:
            return True
        if attempt < attempts - 1 and delay > 0:
            await asyncio.sleep(delay)
    return False

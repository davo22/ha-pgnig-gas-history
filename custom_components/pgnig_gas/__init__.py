"""PGNiG/ORLEN gas history — spreads billing-period readings evenly over time."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started

from .const import CONF_METER, COST_UID_PREFIX, DOMAIN, METER_UID_PREFIX, SERVICE_SYNC
from .statistics import async_sync, entity_for

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=6)
# pgnig-sensor updates its meter and invoice sensors together; sync once after both.
DEBOUNCE_SECONDS = 30

PgnigGasEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: PgnigGasEntry) -> bool:
    """Set up gas history for one meter."""
    meter: str = entry.data[CONF_METER]
    lock = asyncio.Lock()

    async def _sync(_now=None) -> None:
        async with lock:
            try:
                await async_sync(hass, meter)
            except Exception:  # noqa: BLE001 - scheduled task must not die silently
                _LOGGER.exception("Gas history sync failed for meter %s", meter)

    entry.runtime_data = _sync

    cancel_pending = None

    @callback
    def _on_change(_event: Event) -> None:
        nonlocal cancel_pending
        if cancel_pending:
            cancel_pending()
        cancel_pending = async_call_later(hass, DEBOUNCE_SECONDS, _sync)

    @callback
    def _unsub_pending() -> None:
        if cancel_pending:
            cancel_pending()

    watched = [
        eid
        for eid in (
            entity_for(hass, METER_UID_PREFIX, meter),
            entity_for(hass, COST_UID_PREFIX, meter),
        )
        if eid
    ]
    entry.async_on_unload(async_track_state_change_event(hass, watched, _on_change))
    entry.async_on_unload(async_track_time_interval(hass, _sync, UPDATE_INTERVAL))
    entry.async_on_unload(_unsub_pending)

    async def _at_started(_hass: HomeAssistant) -> None:
        await _sync()

    entry.async_on_unload(async_at_started(hass, _at_started))

    _register_service(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PgnigGasEntry) -> bool:
    """Unload a config entry."""
    return True


def _register_service(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SYNC):
        return

    async def _handle(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data()

    hass.services.async_register(DOMAIN, SERVICE_SYNC, _handle)

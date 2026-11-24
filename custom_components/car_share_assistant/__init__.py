"""Car share assistant custom integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_utc_time_change

from .api import ApiError, AuthError, CarShareClient
from .const import DOMAIN, PLATFORMS
from .coordinator import CarShareCoordinator
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
type CarShareConfigEntry = ConfigEntry[CarShareCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CarShareConfigEntry) -> bool:
    client = CarShareClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        info = await client.info()
        if info["instance_id"] != entry.unique_id:
            raise ConfigEntryAuthFailed("Het app-adres verwijst naar een andere installatie.")
    except AuthError:
        raise ConfigEntryAuthFailed("Log opnieuw in met je beheerdersaccount.") from None
    except ApiError:
        raise ConfigEntryNotReady("De Car share assistant-app is niet bereikbaar.") from None
    coordinator = entry.runtime_data = CarShareCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def clock_tick(now):
        # Time-dependent entities change on time, without additional HTTP traffic.
        coordinator.async_update_listeners()
        if coordinator.data["today"] != coordinator.now.date().isoformat():
            entry.async_create_background_task(hass, coordinator.async_request_refresh(), "Refresh Car share month")

    entry.async_on_unload(async_track_utc_time_change(hass, clock_tick, second=0))
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CarShareConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: CarShareConfigEntry) -> None:
    try:
        await CarShareClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]).revoke()
    except ApiError:
        # An offline server cannot be cleaned up. Its administrator can revoke it in the webapp.
        pass

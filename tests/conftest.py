"""Only fake family data and credentials; no production requests."""

import inspect
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from homeassistant import auth, bootstrap, config_entries, loader
from homeassistant.core import HomeAssistant

from custom_components.car_share_assistant.const import DOMAIN

URL = "http://192.0.2.20:8080"
PEOPLE = [
    {"id": "person-a", "name": "Gezinslid A", "username": "testadmin", "role": "admin", "color": "a", "version": 1},
    {"id": "person-b", "name": "Gezinslid B", "username": "testmember", "role": "member", "color": "b", "version": 1},
]
VEHICLES = [{"id": "car-a", "name": "Testauto", "plate": "TEST", "detail": "", "version": 1}]
RESERVATION = {
    "id": "reservation-a",
    "vehicle_id": "car-a",
    "vehicle_name": "Testauto",
    "person_id": "person-b",
    "person_name": "Gezinslid B",
    "start_time": "2026-12-12T09:00:00+01:00",
    "end_time": "2026-12-12T17:00:00+01:00",
    "route": "g1",
    "participants": ["person-b", "person-a"],
    "kilometers": 0,
    "comment": "Samen naar de afspraak",
    "rates": {"zName": "Zuidlaren", "gName": "Groningen", "g": 5},
    "total_cents": 500,
    "shares": [{"person_id": "person-b", "amount_cents": 250}, {"person_id": "person-a", "amount_cents": 250}],
    "status": "active",
    "version": 1,
}
INFO = {
    "api_version": 1,
    "instance_id": "family-test",
    "timezone": "Europe/Amsterdam",
    "permissions": {"read": True, "write_reservations": True},
}


@pytest_asyncio.fixture
async def hass(tmp_path):
    """Use real HA core and registries in a disposable config directory."""
    hass = HomeAssistant(str(tmp_path))
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    result = loader.async_setup(hass)
    if inspect.isawaitable(result):
        await result
    component = Path(__file__).parent.parent / "custom_components" / DOMAIN
    integration = loader.Integration(
        hass,
        "custom_components." + DOMAIN,
        component,
        json.loads((component / "manifest.json").read_text()),
        {p.name for p in component.iterdir()},
    )
    hass.data[loader.DATA_CUSTOM_COMPONENTS] = {DOMAIN: integration}
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await bootstrap.async_load_base_functionality(hass)
    hass.auth = await auth.auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    yield hass
    await hass.async_stop(force=True)
    await hass.async_block_till_done()


@pytest.fixture
def entry(hass):
    result = config_entries.ConfigEntry(
        domain=DOMAIN,
        title="Car share assistant",
        unique_id="family-test",
        version=1,
        minor_version=1,
        source=config_entries.SOURCE_USER,
        options={},
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
        data={"url": URL, "token": "fake-service-credential", "username": "testadmin", "key_id": "fake-key"},
    )
    hass.config_entries._entries[result.entry_id] = result
    return result


@pytest.fixture
def api_mock():
    costs = {
        "people": [
            {
                "person_id": uid,
                "name": "Test",
                "amount_cents": 250,
                "through_today_cents": 100,
                "reservation_count": 2,
                "driver_count": 1,
            }
            for uid in ("person-a", "person-b")
        ]
    }
    values = {
        "info": INFO,
        "state": {"people": PEOPLE, "vehicles": VEHICLES, "rates": {}},
        "reservations": [RESERVATION],
        "costs": costs,
        "login": {"token": "new-fake-token", "key_id": "new-fake-key", "instance_id": "family-test"},
        "revoke": {"ok": True},
        "reservation": RESERVATION,
        "create": {"reservation": RESERVATION},
        "update": {"reservation": RESERVATION},
        "cancel": {"reservation": {**RESERVATION, "status": "cancelled", "version": 2}},
        "availability": {"available": False, "conflicting_reservation_ids": ["reservation-a"]},
    }
    from contextlib import ExitStack

    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(
                patch(
                    "custom_components.car_share_assistant.api.CarShareClient." + name,
                    new=AsyncMock(return_value=value),
                )
            )
            for name, value in values.items()
        }
        stack.enter_context(patch("homeassistant.components.zeroconf.async_setup", return_value=True))
        stack.enter_context(patch("homeassistant.components.network.async_setup", return_value=True))
        yield mocks

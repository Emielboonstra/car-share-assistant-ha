"""Real HA setup, entity state, calendar queries, actions and unloading."""

from datetime import datetime
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.car_share_assistant.api import AuthError, ConflictError, ConnectionError
from custom_components.car_share_assistant.const import DOMAIN
from custom_components.car_share_assistant.coordinator import CarShareCoordinator

from .conftest import PEOPLE, RESERVATION, VEHICLES


def entity_id(hass, platform, kind, uid, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"family-test:{kind}:{uid}:{key}")


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_personal_costs_calendar_read_only_and_unload(hass, entry, api_mock):
    await setup(hass, entry)
    assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 17
    cost = entity_id(hass, "sensor", "person", "person-a", "cost_this_month")
    sensor = hass.states.get(cost)
    assert sensor.state == "2.5"
    assert sensor.attributes["unit_of_measurement"] == "EUR"
    assert sensor.attributes["person_id"] == "person-a"
    assert sensor.attributes["driver_id"] == "person-b"
    calendar = entity_id(hass, "calendar", "vehicle", "car-a", "calendar")
    state = hass.states.get(calendar)
    assert state.attributes["supported_features"] == 0
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": calendar,
            "start_date_time": "2026-12-12T00:00:00+01:00",
            "end_date_time": "2026-12-13T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    event = events[calendar]["events"][0]
    assert event["summary"] == "Gezinslid B"
    assert "Samen naar de afspraak" in event["description"]
    assert event["start"] == RESERVATION["start_time"]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "calendar",
            "create_event",
            {
                "entity_id": calendar,
                "summary": "Not allowed",
                "start_date_time": "2026-12-12T09:00:00+01:00",
                "end_date_time": "2026-12-12T17:00:00+01:00",
            },
            blocking=True,
        )
    api_mock["create"].assert_not_awaited()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(calendar).state == "unavailable"


async def test_create_action_selects_driver_shares_comment_and_refreshes(hass, entry, api_mock):
    await setup(hass, entry)
    registry = dr.async_get(hass)
    auto = registry.async_get_device_by_identifier((DOMAIN, "family-test:vehicle:car-a"), entry.entry_id)
    driver = registry.async_get_device_by_identifier((DOMAIN, "family-test:person:person-b"), entry.entry_id)
    passenger = registry.async_get_device_by_identifier((DOMAIN, "family-test:person:person-a"), entry.entry_id)
    result = await hass.services.async_call(
        DOMAIN,
        "create_reservation",
        {
            "vehicle_id": auto.id,
            "person_id": driver.id,
            "start_time": "2026-12-12T09:00:00+01:00",
            "end_time": "2026-12-12T17:00:00+01:00",
            "route": "g1",
            "participants": [passenger.id, driver.id],
            "comment": "Samen naar de afspraak",
            "idempotency_key": "same-logical-request-123",
        },
        blocking=True,
        return_response=True,
    )
    body, key = api_mock["create"].call_args.args
    assert body["vehicle_id"] == "car-a"
    assert body["person_id"] == "person-b"
    assert body["participants"] == ["person-b", "person-a"]
    assert body["comment"] == "Samen naar de afspraak"
    assert key == "same-logical-request-123"
    assert result["reservation"]["id"] == "reservation-a"
    assert result["synchronized"] is True
    assert api_mock["state"].await_count == 2


async def test_invalid_times_conflicts_and_failed_refresh_do_not_duplicate(hass, entry, api_mock):
    await setup(hass, entry)
    values = {
        "vehicle_id": "car-a",
        "person_id": "person-b",
        "start_time": "2026-12-12T09:00:00+01:00",
        "end_time": "2026-12-12T17:00:00+01:00",
        "route": "other",
        "kilometers": 30,
        "comment": "Test",
    }
    for changed in ({"end_time": "2026-12-12T08:00:00+01:00"}, {"kilometers": 0}, {"person_id": "does-not-exist"}):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, "create_reservation", {**values, **changed}, blocking=True)
    api_mock["create"].assert_not_awaited()
    api_mock["create"].side_effect = ConflictError("Overlap")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "create_reservation", values, blocking=True)
    assert api_mock["create"].await_count == 1
    api_mock["create"].side_effect = None
    api_mock["state"].side_effect = ConnectionError()
    result = await hass.services.async_call(DOMAIN, "create_reservation", values, blocking=True, return_response=True)
    assert result["reservation"]["id"] == "reservation-a"
    assert result["synchronized"] is False
    assert api_mock["create"].await_count == 2


async def test_update_cancel_and_read_actions(hass, entry, api_mock):
    await setup(hass, entry)
    values = {
        "reservation_id": "reservation-a",
        "vehicle_id": "car-a",
        "person_id": "person-b",
        "start_time": "2026-12-12T09:00:00+01:00",
        "end_time": "2026-12-12T17:00:00+01:00",
        "route": "g1",
        "comment": "Bewerkt",
    }
    await hass.services.async_call(DOMAIN, "update_reservation", values, blocking=True)
    assert api_mock["update"].call_args.args[1]["version"] == 1
    result = await hass.services.async_call(
        DOMAIN, "cancel_reservation", {"reservation_id": "reservation-a"}, blocking=True, return_response=True
    )
    api_mock["cancel"].assert_awaited_once_with("reservation-a", 1)
    assert result["reservation"]["status"] == "cancelled"
    result = await hass.services.async_call(
        DOMAIN,
        "check_availability",
        {k: v for k, v in values.items() if k in {"vehicle_id", "start_time", "end_time"}},
        blocking=True,
        return_response=True,
    )
    assert result["available"] is False


async def test_new_vehicle_discovery_and_current_status_on_clock(hass, entry, api_mock):
    with patch.object(
        CarShareCoordinator,
        "now",
        new_callable=PropertyMock,
        return_value=datetime.fromisoformat("2026-12-12T10:00:00+01:00"),
    ) as clock:
        await setup(hass, entry)
        reserved = entity_id(hass, "binary_sensor", "vehicle", "car-a", "reserved")
        assert hass.states.get(reserved).state == "on"
        clock.return_value = datetime.fromisoformat("2026-12-12T17:00:00+01:00")
        entry.runtime_data.async_update_listeners()
        assert hass.states.get(reserved).state == "off"
        api_mock["state"].return_value = {
            "people": PEOPLE,
            "vehicles": [*VEHICLES, {**VEHICLES[0], "id": "car-b", "name": "Tweede testauto"}],
            "rates": {},
        }
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert entity_id(hass, "calendar", "vehicle", "car-b", "calendar")
        assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 22


async def test_revoked_key_starts_reauthentication(hass, entry, api_mock):
    await setup(hass, entry)
    api_mock["state"].side_effect = AuthError()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_cancel_removes_reservation_from_calendar(hass, entry, api_mock):
    await setup(hass, entry)
    calendar = entity_id(hass, "calendar", "vehicle", "car-a", "calendar")
    api_mock["reservations"].return_value = []
    await hass.services.async_call(DOMAIN, "cancel_reservation", {"reservation_id": "reservation-a"}, blocking=True)
    assert hass.states.get(calendar).state == "off"
    assert "message" not in hass.states.get(calendar).attributes
    assert entry.runtime_data.upcoming("vehicle", "car-a") is None


async def test_multiday_action_and_calendar_keep_entire_interval_and_free_costs(hass, entry, api_mock):
    long = {
        **RESERVATION,
        "start_time": "2026-12-11T18:00:00+01:00",
        "end_time": "2026-12-14T09:00:00+01:00",
        "cost_waived": True,
        "total_cents": 0,
    }
    api_mock["reservations"].return_value = [long]
    api_mock["create"].return_value = {"reservation": long}
    await setup(hass, entry)
    result = await hass.services.async_call(
        DOMAIN,
        "create_reservation",
        {
            "vehicle_id": "car-a",
            "person_id": "person-b",
            "start_time": long["start_time"],
            "end_time": long["end_time"],
            "route": "g1",
        },
        blocking=True,
        return_response=True,
    )
    self_body = api_mock["create"].call_args.args[0]
    assert self_body["start_time"] == long["start_time"]
    assert self_body["end_time"] == long["end_time"]
    assert result["reservation"]["total_cents"] == 0
    calendar = entity_id(hass, "calendar", "vehicle", "car-a", "calendar")
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": calendar,
            "start_date_time": "2026-12-12T00:00:00+01:00",
            "end_date_time": "2026-12-13T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    event = events[calendar]["events"][0]
    assert event["start"] == long["start_time"]
    assert event["end"] == long["end_time"]
    assert "gratis voor iedereen" in event["description"]
    api_mock["costs"].return_value = {
        "people": [
            {
                "person_id": p["id"],
                "amount_cents": 0,
                "through_today_cents": 0,
                "reservation_count": 1,
                "driver_count": 1,
            }
            for p in PEOPLE
        ]
    }
    await entry.runtime_data.async_refresh()
    for uid in ["person-a", "person-b"]:
        assert hass.states.get(entity_id(hass, "sensor", "person", uid, "cost_this_month")).state == "0.0"

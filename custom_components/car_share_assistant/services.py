"""Explicit family reservation actions, separate from read-only calendars."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

import probatio as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthError
from .const import DOMAIN

BASE = {vol.Optional("config_entry_id"): cv.string}
TIMES = {vol.Required("start_time"): cv.string, vol.Required("end_time"): cv.string}
BOOKING = {
    vol.Required("vehicle_id"): cv.string,
    vol.Required("person_id"): cv.string,
    **TIMES,
    vol.Required("route"): vol.In(["z1", "z2", "g1", "other"]),
    vol.Optional("participants", default=[]): [cv.string],
    vol.Optional("kilometers", default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
    vol.Optional("comment", default=""): cv.string,
}
SCHEMAS = {
    "create_reservation": vol.Schema({**BASE, **BOOKING, vol.Optional("idempotency_key"): cv.string}),
    "update_reservation": vol.Schema(
        {**BASE, **BOOKING, vol.Required("reservation_id"): cv.string, vol.Optional("version"): cv.positive_int}
    ),
    "cancel_reservation": vol.Schema(
        {**BASE, vol.Required("reservation_id"): cv.string, vol.Optional("version"): cv.positive_int}
    ),
    "check_availability": vol.Schema({**BASE, **TIMES, vol.Required("vehicle_id"): cv.string}),
    "get_reservations": vol.Schema(
        {**BASE, **TIMES, vol.Optional("vehicle_id"): cv.string, vol.Optional("person_id"): cv.string}
    ),
    "refresh": vol.Schema(BASE),
}


def interval(data, zone):
    values = []
    for key in ("start_time", "end_time"):
        value = dt_util.parse_datetime(data[key])
        if not isinstance(value, datetime):
            raise ServiceValidationError("Vul geldige begin- en eindtijden in.")
        if value.tzinfo is None:
            local = value.replace(tzinfo=zone)
            if (
                local.utcoffset() != local.replace(fold=1).utcoffset()
                or local.astimezone(dt_util.UTC).astimezone(zone).replace(tzinfo=None) != value
            ):
                raise ServiceValidationError("Kies tijden buiten het dubbele of ontbrekende uur bij zomer-/wintertijd.")
            value = local
        values.append(value)
    if values[0] >= values[1]:
        raise ServiceValidationError("De begintijd moet vóór de eindtijd liggen.")
    return values


def resolve_id(hass, coordinator, value, kind):
    collection = coordinator.data["vehicles" if kind == "vehicle" else "people"]
    if value in collection:
        return value
    device = dr.async_get(hass).async_get(value)
    prefix = f"{coordinator.instance_id}:{kind}:"
    if device:
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier.startswith(prefix) and identifier[len(prefix) :] in collection:
                return identifier[len(prefix) :]
    raise ServiceValidationError("Kies een bestaande auto of persoon uit deze Car share assistant-installatie.")


@callback
def async_setup_services(hass):
    async def handle(call):
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if entry_id := call.data.get("config_entry_id"):
            entries = [e for e in entries if e.entry_id == entry_id]
        if len(entries) != 1:
            raise ServiceValidationError("Selecteer één geladen Car share assistant-installatie via config_entry_id.")
        entry = entries[0]
        coordinator = entry.runtime_data
        client, data, action = coordinator.client, call.data, call.service
        vehicle = resolve_id(hass, coordinator, data["vehicle_id"], "vehicle") if "vehicle_id" in data else None
        person = resolve_id(hass, coordinator, data["person_id"], "person") if "person_id" in data else None
        try:
            if action == "refresh":
                await coordinator.async_refresh()
                if not coordinator.last_update_success:
                    raise ServiceValidationError("Verversen is niet gelukt. Controleer de verbinding en aanmelding.")
                return None
            if action == "cancel_reservation":
                version = data.get("version")
                if version is None:
                    version = (await client.reservation(data["reservation_id"]))["version"]
                result = await client.cancel(data["reservation_id"], version)
            else:
                start, end = interval(data, coordinator.zone)
                if action == "check_availability":
                    return await client.availability(vehicle, start, end)
                if action == "get_reservations":
                    filters = {key: value for key, value in (("vehicle_id", vehicle), ("person_id", person)) if value}
                    return {"reservations": await client.reservations(start, end, **filters)}
                if start.astimezone(coordinator.zone).date() != end.astimezone(coordinator.zone).date():
                    raise ServiceValidationError("Een reservering moet binnen één lokale dag vallen.")
                if start.second or start.microsecond or end.second or end.microsecond:
                    raise ServiceValidationError("Gebruik hele minuten voor de reservering.")
                if data["route"] == "other" and data["kilometers"] <= 0:
                    raise ServiceValidationError("Vul een afstand groter dan nul in.")
                participants = list(
                    dict.fromkeys(
                        [person, *[resolve_id(hass, coordinator, uid, "person") for uid in data["participants"]]]
                    )
                )
                body = {
                    "vehicle_id": vehicle,
                    "person_id": person,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "route": data["route"],
                    "participants": participants,
                    "kilometers": data["kilometers"],
                    "comment": data["comment"],
                }
                if action == "create_reservation":
                    key = data.get("idempotency_key", str(uuid4()))
                    if not re.fullmatch(r"[A-Za-z0-9-]{16,80}", key):
                        raise ServiceValidationError(
                            "Gebruik een idempotentiesleutel van 16–80 letters, cijfers of koppeltekens."
                        )
                    result = await client.create(body, key)
                    result["idempotency_key"] = key
                else:
                    body["version"] = data.get("version")
                    if body["version"] is None:
                        body["version"] = (await client.reservation(data["reservation_id"]))["version"]
                    result = await client.update(data["reservation_id"], body)
        except AuthError:
            entry.async_start_reauth(hass)
            raise ServiceValidationError("Log opnieuw in bij de Car share assistant-integratie.") from None
        except ApiError as error:
            raise ServiceValidationError(str(error)) from None
        # A successful mutation stays successful even when the subsequent read fails.
        try:
            await coordinator.async_refresh()
            result["synchronized"] = coordinator.last_update_success
        except Exception:
            result["synchronized"] = False
        return result if call.return_response else None

    for action, schema in SCHEMAS.items():
        response = (
            SupportsResponse.ONLY
            if action in {"check_availability", "get_reservations"}
            else SupportsResponse.NONE
            if action == "refresh"
            else SupportsResponse.OPTIONAL
        )
        hass.services.async_register(DOMAIN, action, handle, schema=schema, supports_response=response)

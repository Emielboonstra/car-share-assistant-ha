"""Shared snapshots and period queries, independent of entity count."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthError, CarShareClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import Reservation

LOGGER = logging.getLogger(__name__)


class CarShareCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, entry, client: CarShareClient, info: dict):
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name="Car share assistant",
            update_interval=timedelta(minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client
        self.instance_id = info["instance_id"]
        self.zone = ZoneInfo(info["timezone"])
        self._calendar_cache = {}
        self._calendar_lock = asyncio.Lock()

    @property
    def now(self):
        return dt_util.utcnow().astimezone(self.zone)

    async def _async_update_data(self):
        try:
            now = self.now
            first = now.replace(day=1)
            last_month = (first - timedelta(days=1)).strftime("%Y-%m")
            month = now.strftime("%Y-%m")
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            metadata, reservations, current, previous = await asyncio.gather(
                self.client.state(),
                self.client.reservations(start, start + timedelta(days=365)),
                self.client.costs(month),
                self.client.costs(last_month),
            )
            people = {item["id"]: item for item in metadata["people"]}
            vehicles = {item["id"]: item for item in metadata["vehicles"]}
            parsed = tuple(Reservation.parse(item) for item in reservations if item["status"] == "active")
            self._calendar_cache.clear()
            registry = dr.async_get(self.hass)
            for kind, entries in (("person", people), ("vehicle", vehicles)):
                for uid, item in entries.items():
                    if device := registry.async_get_device_by_identifier(
                        (DOMAIN, f"{self.instance_id}:{kind}:{uid}"), self.config_entry.entry_id
                    ):
                        if device.name != item["name"]:
                            registry.async_update_device(device.id, name=item["name"])
            return {
                "people": people,
                "vehicles": vehicles,
                "reservations": parsed,
                "costs": {item["person_id"]: item for item in current["people"]},
                "previous_costs": {item["person_id"]: item for item in previous["people"]},
                "month": month,
                "today": now.date().isoformat(),
            }
        except AuthError:
            raise ConfigEntryAuthFailed("De koppeling is ingetrokken. Log opnieuw in met een beheerder.") from None
        except (ApiError, KeyError, TypeError, ValueError) as error:
            raise UpdateFailed("Car share assistant kon niet worden bijgewerkt.") from error

    async def calendar_reservations(self, vehicle_id, start, end):
        key = (vehicle_id, start.isoformat(), end.isoformat())
        async with self._calendar_lock:
            cached = self._calendar_cache.get(key)
            if cached and cached[0] > monotonic():
                return cached[1]
            rows = await self.client.reservations(start, end, vehicle_id=vehicle_id)
            result = [Reservation.parse(row) for row in rows if row["status"] == "active"]
            if len(self._calendar_cache) >= 64:
                self._calendar_cache.clear()
            self._calendar_cache[key] = (monotonic() + self.update_interval.total_seconds(), result)
            return result

    def upcoming(self, kind, uid):
        now = self.now
        rows = [
            r
            for r in self.data["reservations"]
            if r.end > now and (r.vehicle_id == uid if kind == "vehicle" else uid in r.participants)
        ]
        return min(rows, key=lambda r: (r.start, r.id)) if rows else None

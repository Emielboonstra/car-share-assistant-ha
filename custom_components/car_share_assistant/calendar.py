"""One strictly read-only calendar for each family vehicle."""

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.exceptions import HomeAssistantError

from .api import ApiError, AuthError
from .entity import CarShareEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def add_vehicles():
        new = set(coordinator.data["vehicles"]) - known
        async_add_entities([CarShareCalendar(coordinator, uid) for uid in sorted(new)])
        known.update(new)

    add_vehicles()
    entry.async_on_unload(coordinator.async_add_listener(add_vehicles))


class CarShareCalendar(CarShareEntity, CalendarEntity):
    _attr_name = None
    _attr_supported_features = 0

    def __init__(self, coordinator, uid):
        super().__init__(coordinator, "vehicle", uid, "calendar")

    def as_event(self, reservation):
        return CalendarEvent(
            start=reservation.start,
            end=reservation.end,
            summary=reservation.person_name,
            uid=reservation.id,
            description=reservation.description(self.coordinator.data["people"]),
        )

    @property
    def event(self):
        row = self.coordinator.upcoming("vehicle", self.uid)
        return self.as_event(row) if row else None

    async def async_get_events(self, hass, start_date, end_date):
        try:
            rows = await self.coordinator.calendar_reservations(self.uid, start_date, end_date)
        except AuthError:
            self.coordinator.config_entry.async_start_reauth(hass)
            raise HomeAssistantError("Log opnieuw in bij Car share assistant.") from None
        except ApiError:
            raise HomeAssistantError("De autokalender kon niet worden opgehaald.") from None
        return [self.as_event(row) for row in rows]

"""Personal reservation costs and current/next vehicle information."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .entity import CarShareEntity

PERSON_KEYS = (
    "cost_this_month",
    "cost_last_month",
    "cost_through_today",
    "rides_this_month",
    "driver_rides_this_month",
    "next_reservation",
)
VEHICLE_KEYS = ("current_driver", "next_start", "next_end")


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def add_entities():
        entities = []
        for kind, collection, keys in (("person", "people", PERSON_KEYS), ("vehicle", "vehicles", VEHICLE_KEYS)):
            for uid in coordinator.data[collection]:
                if (kind, uid) in known:
                    continue
                known.add((kind, uid))
                entities.extend(CarShareSensor(coordinator, kind, uid, key) for key in keys)
        async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class CarShareSensor(CarShareEntity, SensorEntity):
    def __init__(self, coordinator, kind, uid, key):
        super().__init__(coordinator, kind, uid, key)
        self.key = self._attr_translation_key = key
        if key.startswith("cost_"):
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = "EUR"
            self._attr_suggested_display_precision = 2
        elif key in {"next_start", "next_end", "next_reservation"}:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_icon = "mdi:steering" if key == "current_driver" else "mdi:counter"

    @property
    def native_value(self):
        data = self.coordinator.data
        if self.key.startswith("cost_"):
            bucket = "previous_costs" if self.key == "cost_last_month" else "costs"
            field = "through_today_cents" if self.key == "cost_through_today" else "amount_cents"
            cents = data[bucket].get(self.uid, {}).get(field)
            return cents / 100 if cents is not None else None
        if self.key in {"rides_this_month", "driver_rides_this_month"}:
            field = "driver_count" if self.key.startswith("driver_") else "reservation_count"
            return data["costs"].get(self.uid, {}).get(field)
        row = self.coordinator.upcoming(self.kind, self.uid)
        if self.key == "current_driver":
            return row.person_name if row and row.start <= self.coordinator.now < row.end else None
        if not row:
            return None
        return row.end if self.key == "next_end" else row.start

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self.key.startswith("cost_") or self.key.endswith("this_month"):
            attrs["includes_planned_reservations"] = True
        if row := self.coordinator.upcoming(self.kind, self.uid):
            attrs.update(
                reservation_id=row.id,
                vehicle_id=row.vehicle_id,
                driver_id=row.person_id,
                driver=row.person_name,
                start_time=row.start.isoformat(),
                end_time=row.end.isoformat(),
            )
        return attrs

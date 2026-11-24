"""Current reservation status changes on time, without extra requests."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import CarShareEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def add_vehicles():
        new = set(coordinator.data["vehicles"]) - known
        async_add_entities([VehicleReserved(coordinator, uid) for uid in sorted(new)])
        known.update(new)

    add_vehicles()
    entry.async_on_unload(coordinator.async_add_listener(add_vehicles))


class VehicleReserved(CarShareEntity, BinarySensorEntity):
    _attr_translation_key = "reserved"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, uid):
        super().__init__(coordinator, "vehicle", uid, "reserved")

    @property
    def is_on(self):
        row = self.coordinator.upcoming("vehicle", self.uid)
        return bool(row and row.start <= self.coordinator.now < row.end)

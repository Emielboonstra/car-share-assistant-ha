"""Entity identities are independent of names and HA device IDs."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class CarShareEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, kind, uid, key):
        super().__init__(coordinator)
        self.kind, self.uid = kind, uid
        self._attr_unique_id = f"{coordinator.instance_id}:{kind}:{uid}:{key}"

    @property
    def available(self):
        collection = "vehicles" if self.kind == "vehicle" else "people"
        return super().available and self.uid in self.coordinator.data[collection]

    @property
    def device_info(self):
        data = self.coordinator.data["vehicles" if self.kind == "vehicle" else "people"].get(self.uid, {})
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.instance_id}:{self.kind}:{self.uid}")},
            name=data.get("name", self.uid),
            manufacturer="Car share assistant",
            model="Gezinsauto" if self.kind == "vehicle" else "Gezinslid",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=self.coordinator.client.url,
        )

    @property
    def extra_state_attributes(self):
        return {"vehicle_id" if self.kind == "vehicle" else "person_id": self.uid}

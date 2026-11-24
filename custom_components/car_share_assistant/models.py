"""Calendar and cost models shared by entities and actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .api import ApiError


@dataclass(frozen=True, slots=True)
class Reservation:
    id: str
    vehicle_id: str
    vehicle_name: str
    person_id: str
    person_name: str
    start: datetime
    end: datetime
    participants: tuple[str, ...]
    comment: str
    route: str
    kilometers: float
    rates: dict
    version: int

    @classmethod
    def parse(cls, data: dict) -> Reservation:
        try:
            start, end = datetime.fromisoformat(data["start_time"]), datetime.fromisoformat(data["end_time"])
            if start.tzinfo is None or end.tzinfo is None or end <= start:
                raise ValueError
            return cls(
                data["id"],
                data["vehicle_id"],
                data["vehicle_name"],
                data["person_id"],
                data["person_name"],
                start,
                end,
                tuple(data["participants"]),
                data["comment"],
                data["route"],
                data["kilometers"],
                data["rates"],
                data["version"],
            )
        except KeyError, ValueError, TypeError:
            raise ApiError("De app gaf een ongeldig reserveringsmodel terug.") from None

    def description(self, people: dict[str, dict]) -> str:
        z, g = self.rates.get("zName", "Bestemming 1"), self.rates.get("gName", "Bestemming 2")
        route = {"z1": f"1× {z} retour", "z2": f"2× {z} retour", "g1": f"1× {g} retour"}.get(
            self.route, f"Anders: {self.kilometers} km"
        )
        names = ", ".join(people.get(uid, {}).get("name", uid) for uid in self.participants)
        return f"Auto: {self.vehicle_name}\nBestuurder: {self.person_name}\nRit: {route}\nDeelnemers: {names}\nOpmerking: {self.comment}"

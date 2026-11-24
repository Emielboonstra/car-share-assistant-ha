"""Async API client. Never retry a mutation or follow credential redirects."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import aiohttp


class ApiError(Exception):
    """Invalid server response or rejected request."""


class AuthError(ApiError):
    """Credentials invalid or revoked."""


class PermissionError(ApiError):
    """Administrator or reservation permission required."""


class ConnectionError(ApiError):
    """Network failure; a mutation may already have succeeded."""


class ConflictError(ApiError):
    """Reservation conflict, version conflict or key reuse."""


class ServerUpdateRequired(ApiError):
    """The webapp needs the administrator-login endpoint."""


def normalize_url(value: str) -> str:
    """Accept an HTTP(S) origin without embedded credentials or query strings."""
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or (port is not None and port < 1)
        ):
            raise ValueError
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    except ValueError:
        raise ApiError("Vul het volledige HTTP- of HTTPS-adres van de app in.") from None


class CarShareClient:
    """A credential belongs to one explicit Car share assistant instance."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str = "") -> None:
        self.session = session
        self.url = normalize_url(url)
        self.token = token

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict | None = None,
        key: str | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {"X-Carshare-Request": "1"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        if key:
            headers["Idempotency-Key"] = key
        try:
            async with self.session.request(
                method,
                self.url + path,
                json=body,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise AuthError("Gebruikersnaam of wachtwoord klopt niet, of de koppeling is ingetrokken.")
                if response.status == 403:
                    raise PermissionError("Gebruik een beheerdersaccount met reserveringsrechten.")
                if response.status == 409:
                    raise ConflictError(
                        "De auto is al gereserveerd, de rit is gewijzigd of de verzoekcode is al gebruikt."
                    )
                if response.status == 404 and path == "/api/v1/auth/login":
                    raise ServerUpdateRequired("Werk de Car share assistant-webapp bij naar versie 0.3.0 of hoger.")
                if response.status >= 500:
                    raise ConnectionError(
                        "De server heeft een tijdelijke fout. Controleer de rit voordat je opnieuw opslaat."
                    )
                if response.status == 429:
                    raise ApiError("Te veel inlogpogingen. Wacht een kwartier voordat je opnieuw inlogt.")
                if response.status >= 300:
                    raise ApiError(
                        "De server heeft het verzoek geweigerd. Controleer het adres, de ritgegevens en de versie."
                    )
                result = await response.json()
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except aiohttp.ClientError, asyncio.TimeoutError:
            raise ConnectionError(
                "Geen verbinding met de app. Een verzonden wijziging kan al zijn opgeslagen; controleer eerst de reservering."
            ) from None
        except ValueError, TypeError:
            raise ApiError("De app gaf een ongeldig antwoord.") from None

    async def login(self, username: str, password: str) -> dict:
        result = await self.request(
            "POST",
            "/api/v1/auth/login",
            authenticated=False,
            body={"username": username, "password": password, "name": "Home Assistant"},
        )
        try:
            self.token = result["token"]
            info = await self.info()
            if info.get("api_version") != 1 or not info.get("permissions", {}).get("write_reservations"):
                raise PermissionError("Deze koppeling heeft geen reserveringsrechten.")
            return {"token": self.token, "key_id": result["key_id"], "instance_id": info["instance_id"]}
        except KeyError, ApiError:
            if self.token:
                try:
                    await self.revoke()
                except ApiError:
                    pass
            raise ApiError("De koppeling kon niet worden ingesteld. Controleer de app-versie en rechten.") from None

    async def revoke(self) -> dict:
        return await self.request("DELETE", "/api/v1/auth/key")

    async def info(self) -> dict:
        result = await self.request("GET", "/api/v1/info")
        if result.get("api_version") != 1 or not result.get("instance_id"):
            raise ApiError("Deze API-versie wordt niet ondersteund.")
        return result

    async def state(self) -> dict:
        return await self.request("GET", "/api/v1/state")

    async def costs(self, month: str) -> dict:
        return await self.request("GET", "/api/v1/costs", params={"month": month})

    async def reservations(self, start: datetime, end: datetime, **filters) -> list[dict]:
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ApiError("Geef een geldig tijdsbereik met tijdzone op.")
        found = {}
        while start < end:
            finish = min(start + timedelta(days=365), end)
            offset = 0
            while True:
                result = await self.request(
                    "GET",
                    "/api/v1/reservations",
                    params={
                        "start": start.isoformat(),
                        "end": finish.isoformat(),
                        "limit": 500,
                        "offset": offset,
                        **filters,
                    },
                )
                rows = result.get("reservations")
                if not isinstance(rows, list):
                    raise ApiError("De app gaf geen geldige reserveringen terug.")
                try:
                    for row in rows:
                        found[row["id"]] = row
                except KeyError, TypeError:
                    raise ApiError("De app gaf een ongeldige reservering terug.") from None
                next_offset = result.get("next_offset")
                if next_offset is None:
                    break
                if type(next_offset) is not int or next_offset <= offset:
                    raise ApiError("Ongeldige paginering in het API-antwoord.")
                offset = next_offset
            start = finish
        return sorted(found.values(), key=lambda item: (item["start_time"], item["id"]))

    async def reservation(self, reservation_id: str) -> dict:
        from urllib.parse import quote

        return await self.request("GET", "/api/v1/reservations/" + quote(reservation_id, safe=""))

    async def create(self, body: dict, key: str) -> dict:
        return await self.request("POST", "/api/v1/reservations", body=body, key=key)

    async def update(self, reservation_id: str, body: dict) -> dict:
        from urllib.parse import quote

        return await self.request("PUT", "/api/v1/reservations/" + quote(reservation_id, safe=""), body=body)

    async def cancel(self, reservation_id: str, version: int) -> dict:
        from urllib.parse import quote

        return await self.request(
            "DELETE", "/api/v1/reservations/" + quote(reservation_id, safe=""), params={"version": version}
        )

    async def availability(self, vehicle_id: str, start: datetime, end: datetime) -> dict:
        return await self.request(
            "GET",
            "/api/v1/availability",
            params={"vehicle_id": vehicle_id, "start": start.isoformat(), "end": end.isoformat()},
        )

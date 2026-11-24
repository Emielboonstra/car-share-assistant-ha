"""Exercise the client over real loopback HTTP, with fictitious responses."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from custom_components.car_share_assistant.api import (
    ApiError,
    AuthError,
    CarShareClient,
    ConflictError,
    ConnectionError,
    normalize_url,
)

from .conftest import INFO, RESERVATION


@pytest_asyncio.fixture
async def server():
    replies, requests = [], []

    async def handler(request):
        requests.append(
            {
                "path": request.path,
                "method": request.method,
                "query": dict(request.query),
                "headers": dict(request.headers),
                "body": await request.json() if request.can_read_body else None,
            }
        )
        status, body = replies.pop(0)
        return web.json_response(body, status=status)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    yield f"http://127.0.0.1:{runner.addresses[0][1]}", replies, requests
    await runner.cleanup()


async def test_login_uses_password_once_and_does_not_store_it(server):
    url, replies, requests = server
    replies.extend([(201, {"token": "fake-token", "key_id": "fake-key"}), (200, INFO)])
    async with aiohttp.ClientSession() as session:
        client = CarShareClient(session, url)
        result = await client.login("testadmin", "fake-password")
        assert result["instance_id"] == "family-test"
        assert requests[0]["body"]["password"] == "fake-password"
        assert "Authorization" not in requests[0]["headers"]
        assert requests[1]["headers"]["Authorization"] == "Bearer fake-token"
        assert "password" not in client.__dict__


async def test_pagination_deduplicates_and_filters(server):
    url, replies, requests = server
    replies.extend(
        [
            (200, {"reservations": [RESERVATION], "next_offset": 500}),
            (200, {"reservations": [RESERVATION, {**RESERVATION, "id": "second"}], "next_offset": None}),
        ]
    )
    async with aiohttp.ClientSession() as session:
        result = await CarShareClient(session, url, "fake-token").reservations(
            datetime.fromisoformat("2026-12-12T00:00:00+01:00"),
            datetime.fromisoformat("2026-12-13T00:00:00+01:00"),
            vehicle_id="car-a",
        )
    assert len(result) == 2
    assert requests[0]["query"]["vehicle_id"] == "car-a"
    assert requests[1]["query"]["offset"] == "500"


@pytest.mark.parametrize(
    ("status", "error"), [(401, AuthError), (409, ConflictError), (500, ConnectionError), (302, ApiError)]
)
async def test_mutation_failures_are_never_retried_or_redirected(server, status, error):
    url, replies, requests = server
    replies.append((status, {}))
    async with aiohttp.ClientSession() as session:
        client = CarShareClient(session, url, "fake-token")
        with pytest.raises(error):
            await client.create({"comment": "kept"}, "same-logical-request-123")
    assert len(requests) == 1
    assert requests[0]["headers"]["Idempotency-Key"] == "same-logical-request-123"


async def test_timeout_is_uncertain_not_retried():
    async with aiohttp.ClientSession() as session:
        with patch.object(session, "request", side_effect=asyncio.TimeoutError()) as request:
            with pytest.raises(ConnectionError):
                await CarShareClient(session, "http://127.0.0.1", "fake-token").create({}, "same-logical-request-123")
            assert request.call_count == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.test",
        "http://example.test/?token=secret",
        "file:///etc/passwd",
        "https://example.test/app",
        "not-a-url",
    ],
)
def test_rejects_credential_urls_and_non_origins(url):
    with pytest.raises(ApiError):
        normalize_url(url)

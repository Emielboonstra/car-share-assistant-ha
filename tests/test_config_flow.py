from ipaddress import IPv4Address
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.car_share_assistant.api import AuthError, PermissionError
from custom_components.car_share_assistant.const import DOMAIN

from .conftest import URL


@pytest.mark.parametrize("public_url", [None, "https://car.example.test"])
async def test_discovered_login_has_no_address_or_stored_password(hass, api_mock, public_url):
    discovered = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.0.2.20"),
        ip_addresses=[IPv4Address("192.0.2.20")],
        port=8080,
        hostname="car-share-assistant.local.",
        type="_carshare._tcp.local.",
        name="Car share assistant._carshare._tcp.local.",
        properties={"id": "family-test"},
    )
    if public_url:
        discovered.properties["url"] = public_url
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovered)
    assert result["step_id"] == "login"
    assert "url" not in result["data_schema"]({"username": "testadmin", "password": "fake-password"})
    with patch("custom_components.car_share_assistant.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "testadmin", "password": "fake-password"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "password" not in result["data"]
    assert result["data"]["url"] == (public_url or URL)
    assert result["data"]["token"] == "new-fake-token"


async def test_user_flow_auto_discovers_and_handles_invalid_login(hass, api_mock):
    with patch(
        "custom_components.car_share_assistant.config_flow.async_discover",
        return_value={"family-test": {"url": URL, "name": "Test app"}},
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "login"
    api_mock["login"].side_effect = AuthError()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "testadmin", "password": "fake-password"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    api_mock["login"].side_effect = PermissionError()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "testmember", "password": "fake-password"}
    )
    assert result["errors"] == {"base": "admin_required"}


async def test_manual_fallback_duplicate_cleanup(hass, api_mock, entry):
    with patch("custom_components.car_share_assistant.config_flow.async_discover", return_value={}):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "discover"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "testadmin", "password": "fake-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    api_mock["revoke"].assert_awaited_once()


async def test_reconfigure_same_instance_only(hass, api_mock, entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "reconfigure"
    api_mock["info"].return_value = {"api_version": 1, "instance_id": "other-instance"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://car.example.test"})
    assert result["errors"] == {"base": "wrong_instance"}
    api_mock["info"].return_value = {"api_version": 1, "instance_id": "family-test"}
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://car.example.test"})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["url"] == "https://car.example.test"
    assert entry.data["token"] == "fake-service-credential"


async def test_reauthentication_replaces_key_without_password(hass, api_mock, entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data
    )
    assert result["step_id"] == "login"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "testadmin", "password": "fake-password"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-fake-token"
    assert "password" not in entry.data

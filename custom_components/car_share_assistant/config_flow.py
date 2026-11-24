"""Log in as a webapp administrator; persist only a service credential."""

from __future__ import annotations

import logging

import probatio as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ApiError,
    AuthError,
    CarShareClient,
    ConnectionError,
    PermissionError,
    ServerUpdateRequired,
    normalize_url,
)
from .const import CONF_KEY_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .discovery import async_discover

LOGGER = logging.getLogger(__name__)


class CarShareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _url = None
    _discovered_id = None
    _found = None

    async def async_step_user(self, user_input=None):
        if self.source == config_entries.SOURCE_REAUTH:
            self._url = self._get_reauth_entry().data[CONF_URL]
            return await self.async_step_login(user_input)
        try:
            self._found = await async_discover(self.hass)
        except OSError:
            self._found = {}
        if len(self._found) == 1:
            self._discovered_id, found = next(iter(self._found.items()))
            self._url = found["url"]
            return await self.async_step_login()
        if self._found:
            return await self.async_step_select()
        return await self.async_step_discover()

    async def async_step_discover(self, user_input=None):
        return self.async_show_menu(step_id="discover", menu_options=["search", "manual"])

    async def async_step_search(self, user_input=None):
        return await self.async_step_user()

    async def async_step_select(self, user_input=None):
        if user_input is not None:
            self._discovered_id = user_input["server"]
            self._url = self._found[self._discovered_id]["url"]
            return await self.async_step_login()
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {vol.Required("server"): vol.In({uid: item["name"] for uid, item in self._found.items()})}
            ),
        )

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self._url = normalize_url(user_input[CONF_URL])
            except ApiError:
                errors["base"] = "invalid_response"
            else:
                return await self.async_step_login()
        return self.async_show_form(
            step_id="manual", errors=errors, data_schema=vol.Schema({vol.Required(CONF_URL): str})
        )

    async def async_step_zeroconf(self, discovery_info):
        self._discovered_id = discovery_info.properties.get("id")
        if not self._discovered_id or not discovery_info.port:
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(self._discovered_id)
        self._abort_if_unique_id_configured()
        host = str(discovery_info.ip_address)
        host = f"[{host}]" if ":" in host else host
        self._url = f"http://{host}:{discovery_info.port}"
        if advertised := discovery_info.properties.get("url"):
            try:
                self._url = normalize_url(advertised)
            except ApiError:
                return self.async_abort(reason="invalid_discovery")
        self.context["title_placeholders"] = {"name": "Car share assistant"}
        return await self.async_step_login()

    async def async_step_login(self, user_input=None):
        errors = {}
        entry = (
            self._get_reauth_entry()
            if self.source == config_entries.SOURCE_REAUTH
            else self._get_reconfigure_entry()
            if self.source == config_entries.SOURCE_RECONFIGURE
            else None
        )
        if user_input is not None:
            try:
                client = CarShareClient(async_get_clientsession(self.hass), self._url)
                result = await client.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except AuthError:
                errors["base"] = "invalid_auth"
            except PermissionError:
                errors["base"] = "admin_required"
            except ServerUpdateRequired:
                errors["base"] = "server_update_required"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except ApiError:
                errors["base"] = "invalid_response"
            else:
                instance = result["instance_id"]
                await self.async_set_unique_id(instance)
                wrong_instance = (entry and entry.unique_id != instance) or (
                    self._discovered_id and self._discovered_id != instance
                )
                if wrong_instance or (
                    not entry and any(e.unique_id == instance for e in self._async_current_entries())
                ):
                    try:
                        await client.revoke()
                    except ApiError:
                        pass
                    return self.async_abort(reason="wrong_instance" if wrong_instance else "already_configured")
                data = {
                    CONF_URL: client.url,
                    CONF_TOKEN: result["token"],
                    CONF_KEY_ID: result["key_id"],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                }
                if entry:
                    try:
                        await CarShareClient(
                            async_get_clientsession(self.hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]
                        ).revoke()
                    except ApiError:
                        pass
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                return self.async_create_entry(title="Car share assistant", data=data)
        defaults = user_input or (entry.data if entry else {})
        return self.async_show_form(
            step_id="login",
            errors=errors,
            description_placeholders={"url": self._url},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
                    vol.Required(vol.Secret(CONF_PASSWORD)): str,
                }
            ),
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                client = CarShareClient(
                    async_get_clientsession(self.hass), user_input[CONF_URL], entry.data[CONF_TOKEN]
                )
                info = await client.info()
                if info["instance_id"] != entry.unique_id:
                    errors["base"] = "wrong_instance"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_URL: client.url})
            except AuthError:
                self._url = client.url
                return await self.async_step_login()
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except ApiError:
                errors["base"] = "invalid_response"
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_URL, default=entry.data[CONF_URL]): str}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CarShareOptionsFlow()


class CarShareOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
        )

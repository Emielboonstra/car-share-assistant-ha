"""Use Home Assistant's shared zeroconf instance; do not scan arbitrary hosts."""

import asyncio

from homeassistant.components.zeroconf import async_get_async_instance
from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser

from .api import ApiError, normalize_url

SERVICE_TYPE = "_carshare._tcp.local."


async def async_discover(hass):
    zeroconf = await async_get_async_instance(hass)
    names = set()

    def changed(zeroconf, service_type, name, state_change):
        if state_change is not ServiceStateChange.Removed:
            names.add(name)

    browser = AsyncServiceBrowser(zeroconf.zeroconf, SERVICE_TYPE, handlers=[changed])
    try:
        await asyncio.sleep(2)
        infos = await asyncio.gather(
            *(zeroconf.async_get_service_info(SERVICE_TYPE, name, timeout=1500) for name in sorted(names))
        )
    finally:
        await browser.async_cancel()
    found = {}
    for info in infos:
        if not info or not info.port:
            continue
        addresses = info.parsed_addresses(IPVersion.V4Only)
        if not addresses:
            continue
        instance = info.decoded_properties.get("id")
        if instance:
            url = f"http://{addresses[0]}:{info.port}"
            if advertised := info.decoded_properties.get("url"):
                try:
                    url = normalize_url(advertised)
                except ApiError:
                    continue
            found[instance] = {
                "url": url,
                "name": info.name.removesuffix("." + SERVICE_TYPE),
            }
    return found

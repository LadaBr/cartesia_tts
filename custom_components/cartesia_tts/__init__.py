from dataclasses import dataclass
from cartesia import AsyncCartesia
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from .const import CONF_MODEL, CONF_VOICE

PLATFORMS = [Platform.TTS]

@dataclass
class CartesiaData:
    client: AsyncCartesia

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    httpx_client = get_async_client(hass)
    client = AsyncCartesia(api_key=entry.data[CONF_API_KEY], httpx_client=httpx_client)
    entry.runtime_data = CartesiaData(client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
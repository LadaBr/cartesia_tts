from dataclasses import dataclass
from cartesia import AsyncCartesia
import os
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from .const import DOMAIN, VOICES_CACHE_FILE

PLATFORMS = [Platform.TTS]

@dataclass
class CartesiaData:
    client: AsyncCartesia

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    httpx_client = get_async_client(hass)
    
    client = AsyncCartesia(api_key=entry.data[CONF_API_KEY], httpx_client=httpx_client)
    
    setattr(entry, "runtime_data", CartesiaData(client=client))
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Registrace služby refresh_voices (pouze jednou)
    if not hass.services.has_service(DOMAIN, "refresh_voices"):
        async def _handle_refresh_voices(call):
            cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
            if os.path.exists(cache_file):
                os.remove(cache_file)
            
            entries = hass.config_entries.async_entries(DOMAIN)
            for e in entries:
                await hass.config_entries.async_reload(e.entry_id)
        
        hass.services.async_register(DOMAIN, "refresh_voices", _handle_refresh_voices)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
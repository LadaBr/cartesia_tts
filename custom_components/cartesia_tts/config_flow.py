from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
import voluptuous as vol
import os
import json
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from .const import SUPPORTED_LANGUAGES, VOICES_CACHE_FILE, CONF_LANGUAGE

USER_STEP_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): str,
    vol.Optional(CONF_LANGUAGE, "en"): vol.In(SUPPORTED_LANGUAGES)
})

async def get_voices_models(hass: HomeAssistant, api_key: str, language: str):
    cache_key = f"{api_key}_{language}"
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    
    # Try to load from cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if cache.get("cache_key") == cache_key:
                    voices_dict = cache.get("voices", {})
                    models_dict = {"sonic-3": "sonic-3", "sonic-2": "sonic-2"}
                    return voices_dict, models_dict
        except:
            pass
    
    # Fetch from API
    httpx_client = get_async_client(hass)
    client = AsyncCartesia(api_key=api_key, httpx_client=httpx_client)
    voices_pager = await client.voices.list()
    voices = [v async for v in voices_pager]
    
    # Filter by language
    filtered_voices = []
    for v in voices:
        langs = getattr(v, "language", [])
        if isinstance(langs, str):
            langs = [langs]
        if language in langs or "multilingual" in getattr(v, "mode", ""):
            filtered_voices.append(v)
    
    voices_dict = {getattr(voice, 'id'): getattr(voice, 'name') for voice in filtered_voices}
    models_dict = {"sonic-3": "sonic-3", "sonic-2": "sonic-2"}
    
    # Save to cache
    try:
        with open(cache_file, "w") as f:
            json.dump({"cache_key": cache_key, "voices": voices_dict}, f)
    except:
        pass
    
    return voices_dict, models_dict

class CartesiaConfigFlow(ConfigFlow, domain="cartesia_tts"):
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                language = user_input.get(CONF_LANGUAGE, "en")
                voices, models = await get_voices_models(self.hass, user_input[CONF_API_KEY], language)
                return self.async_create_entry(
                    title="Cartesia",
                    data=user_input,
                    options={"model": "sonic-3", "voice": list(voices.keys())[0] if voices else "", "language": language},
                )
            except ApiError:
                errors["base"] = "invalid_api_key"
        return self.async_show_form(step_id="user", data_schema=USER_STEP_SCHEMA, errors=errors)
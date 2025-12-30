from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
import voluptuous as vol
import os
import json
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from .const import VOICES_CACHE_FILE

async def get_all_voices(hass: HomeAssistant, api_key: str):
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    
    # Try to load from cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if cache.get("api_key") == api_key:
                    return cache.get("voices", [])
        except:
            pass
    
    # Fetch from API
    httpx_client = get_async_client(hass)
    client = AsyncCartesia(api_key=api_key, httpx_client=httpx_client)
    voices_pager = await client.voices.list()
    voices = [v async for v in voices_pager]
    
    voices_list = []
    for v in voices:
        voices_list.append({
            "id": getattr(v, 'id'),
            "name": getattr(v, 'name'),
            "language": getattr(v, 'language', []),
            "is_custom": getattr(v, 'is_custom', False),
            "mode": getattr(v, 'mode', ""),
        })
    
    # Save to cache
    try:
        with open(cache_file, "w") as f:
            json.dump({"api_key": api_key, "voices": voices_list}, f)
    except:
        pass
    
    return voices_list

class CartesiaTTSConfigFlow(ConfigFlow, domain="cartesia_tts"):
    VERSION = 1

    def __init__(self):
        self.api_key = None
        self.voices = []
        self.entities = []
        self.current_entity = {}

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_API_KEY): str,
                }),
            )
        
        self.api_key = user_input[CONF_API_KEY]
        
        # Validate API key by fetching voices
        try:
            self.voices = await get_all_voices(self.hass, self.api_key)
            if not self.voices:
                raise ValueError("No voices found")
        except Exception as e:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_API_KEY): str,
                }),
                errors={CONF_API_KEY: "invalid_api_key"},
            )
        
        return await self.async_step_entity()

    async def async_step_reconfigure(self, user_input=None):
        self.config_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self.api_key = self.config_entry.data["api_key"]
        self.entities = self.config_entry.data["entities"].copy()
        
        # Fetch voices if not already
        if not self.voices:
            try:
                self.voices = await get_all_voices(self.hass, self.api_key)
            except:
                return self.async_abort(reason="cannot_connect")
        
        return await self.async_step_entity()

    async def async_step_entity(self, user_input=None):
        if user_input is None:
            languages = sorted(set(lang for v in self.voices for lang in (v["language"] if isinstance(v["language"], list) else [v["language"]])))
            default_name = f"TTS {len(self.entities) + 1}"
            return self.async_show_form(
                step_id="entity",
                data_schema=vol.Schema({
                    vol.Optional("name", default=default_name): str,
                    vol.Required("language"): vol.In(languages),
                }),
            )
        
        name = user_input.get("name", f"TTS {len(self.entities) + 1}")
        self.current_entity = {"name": name, "language": user_input["language"]}
        return await self.async_step_voice()

    async def async_step_voice(self, user_input=None):
        if user_input is None:
            voices_for_lang = []
            for v in self.voices:
                langs = v["language"] if isinstance(v["language"], list) else [v["language"]]
                if self.current_entity["language"] in langs or "multilingual" in v.get("mode", ""):
                    voices_for_lang.append(v)
            
            # Sort: custom voices first
            custom_voices = [v for v in voices_for_lang if v.get("is_custom", False)]
            standard_voices = [v for v in voices_for_lang if not v.get("is_custom", False)]
            voices_options = {v["id"]: v["name"] for v in custom_voices + standard_voices}
            
            return self.async_show_form(
                step_id="voice",
                data_schema=vol.Schema({
                    vol.Required("voice"): vol.In(voices_options),
                }),
            )
        
        self.current_entity["voice"] = user_input["voice"]
        self.entities.append(self.current_entity)
        
        return await self.async_step_add_another()

    async def async_step_add_another(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="add_another",
                data_schema=vol.Schema({
                    vol.Required("add_another", default=False): bool,
                }),
            )
        
        if user_input["add_another"]:
            return await self.async_step_entity()
        
        if self.config_entry:
            # Reconfigure
            new_data = {"api_key": self.api_key, "entities": self.entities}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")
        else:
            return self.async_create_entry(
                title="Cartesia TTS",
                data={"api_key": self.api_key, "entities": self.entities},
            )

class CartesiaTTSOptionsFlow(OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        # For now, just return empty, or implement options if needed
        return self.async_create_entry(title="", data={})
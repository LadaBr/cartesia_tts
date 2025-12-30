from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.httpx_client import get_async_client

USER_STEP_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})

async def get_voices_models(hass: HomeAssistant, api_key: str):
    httpx_client = get_async_client(hass)
    client = AsyncCartesia(api_key=api_key, httpx_client=httpx_client)
    voices = [v async for v in client.voices.list()]
    models = ["sonic-3", "sonic-2"]  # Available models
    voices_dict = {voice.id: voice.name for voice in voices}
    models_dict = {model: model for model in models}
    return voices_dict, models_dict

class CartesiaConfigFlow(ConfigFlow, domain="cartesia_tts"):
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                voices, models = await get_voices_models(self.hass, user_input[CONF_API_KEY])
                return self.async_create_entry(
                    title="Cartesia",
                    data=user_input,
                    options={"model": "sonic-3", "voice": list(voices.keys())[0] if voices else ""},
                )
            except ApiError:
                errors["base"] = "invalid_api_key"
        return self.async_show_form(step_id="user", data_schema=USER_STEP_SCHEMA, errors=errors)
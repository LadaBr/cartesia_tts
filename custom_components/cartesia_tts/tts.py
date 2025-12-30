from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
from homeassistant.components.tts import TextToSpeechEntity, TtsAudioType, Voice
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import os
import json
from .const import VOICES_CACHE_FILE, CONF_LANGUAGE

class CartesiaTTSEntity(TextToSpeechEntity):
    _attr_supported_options = ["voice", "model"]
    _attr_supported_languages = ["cs", "en", "de", "es", "fr", "it", "pl", "pt", "zh", "ja"]
    
    def __init__(self, client: AsyncCartesia, voices, default_voice_id: str, entry_id: str, language: str):
        self._client = client
        self._default_voice_id = default_voice_id
        self._voices = voices
        self._attr_name = "Cartesia TTS"
        self._attr_unique_id = entry_id
        self._language = language
        
    @property
    def supported_languages(self) -> list[str]:
        return self._attr_supported_languages
    
    @property
    def default_language(self) -> str:
        return "en"
        
    async def async_get_tts_audio(self, message: str, language: str, options: dict) -> TtsAudioType:
        voice_id = options.get("voice", self._default_voice_id)
        model = options.get("model", "sonic-3")
        try:
            audio_iter = self._client.tts.bytes(
                model_id=model,
                transcript=message,
                voice={"mode": "id", "id": voice_id},
                language=self._language,
                output_format={"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100},
            )
            bytes_combined = b""
            async for chunk in audio_iter:
                bytes_combined += chunk
            return "wav", bytes_combined
        except ApiError as exc:
            raise HomeAssistantError(exc) from exc

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    data = getattr(config_entry, 'runtime_data')
    language = config_entry.options.get(CONF_LANGUAGE, "en")
    api_key = config_entry.data[CONF_API_KEY]
    cache_key = f"{api_key}_{language}"
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    
    # Try to load from cache
    voices = []
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if cache.get("cache_key") == cache_key:
                    voices_dict = cache.get("voices", {})
                    voices = [Voice(vid, name) for vid, name in voices_dict.items()]
        except:
            pass
    
    if not voices:
        # Fetch from API
        voices_pager = await data.client.voices.list()
        all_voices = [v async for v in voices_pager]
        
        # Filter by language
        filtered_voices = []
        for v in all_voices:
            langs = getattr(v, "language", [])
            if isinstance(langs, str):
                langs = [langs]
            if language in langs or "multilingual" in getattr(v, "mode", ""):
                filtered_voices.append(v)
        
        voices = [Voice(getattr(v, 'id'), getattr(v, 'name')) for v in filtered_voices]
        
        # Save to cache
        voices_dict = {getattr(v, 'id'): getattr(v, 'name') for v in voices}
        try:
            with open(cache_file, "w") as f:
                json.dump({"cache_key": cache_key, "voices": voices_dict}, f)
        except:
            pass
    
    async_add_entities([CartesiaTTSEntity(data.client, voices, config_entry.options.get("voice", ""), config_entry.entry_id, language)])
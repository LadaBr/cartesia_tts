from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
from homeassistant.components.tts import TextToSpeechEntity, TtsAudioType, Voice
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import os
import json
from .const import VOICES_CACHE_FILE

class CartesiaTTSEntity(TextToSpeechEntity):
    _attr_supported_options = ["voice", "model"]
    
    def __init__(self, client: AsyncCartesia, voices, voice_id: str, unique_id: str, language: str, name: str):
        self._client = client
        self._voice_id = voice_id
        self._voices = voices
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._language = language
        
    @property
    def supported_languages(self) -> list[str]:
        return [self._language]
    
    @property
    def default_language(self) -> str:
        return self._language
        
    async def async_get_tts_audio(self, message: str, language: str, options: dict) -> TtsAudioType:
        voice_id = options.get("voice", self._voice_id)
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
    api_key = config_entry.data[CONF_API_KEY]
    entities = []
    
    for i, entity_config in enumerate(data.entities):
        language = entity_config["language"]
        voice_id = entity_config["voice"]
        name = entity_config["name"]
        unique_id = f"{config_entry.entry_id}_{i}"
        
        # Fetch voices for this language
        cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
        cache_key = api_key
        
        # Try to load from cache
        voices = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cache = json.load(f)
                    if cache.get("api_key") == api_key:
                        all_voices = cache.get("voices", [])
                        # Filter for language
                        for v in all_voices:
                            langs = v["language"] if isinstance(v["language"], list) else [v["language"]]
                            if language in langs or "multilingual" in v.get("mode", ""):
                                voices.append(Voice(v["id"], v["name"]))
            except:
                pass
        
        if not voices:
            # Fetch from API if not cached
            voices_pager = await data.client.voices.list()
            all_voices = [v async for v in voices_pager]
            
            for v in all_voices:
                langs = getattr(v, "language", [])
                if isinstance(langs, str):
                    langs = [langs]
                if language in langs or "multilingual" in getattr(v, "mode", ""):
                    voices.append(Voice(getattr(v, 'id'), getattr(v, 'name')))
        
        entities.append(CartesiaTTSEntity(data.client, voices, voice_id, unique_id, language, name))
    
    async_add_entities(entities)
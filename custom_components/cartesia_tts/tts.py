from typing import Any  # <--- PŘIDÁNO PRO OPRAVU TYPOVÁNÍ
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
    # Podporujeme změnu hlasu i modelu přes service call
    _attr_supported_options = ["voice", "model", "speed"]
    
    def __init__(self, client: AsyncCartesia, voices, voice_id: str, unique_id: str, language: str, name: str, speed: float = 1.0):
        self._client = client
        self._voice_id = voice_id
        self._voices = voices
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._language = language
        self._speed = speed
        
    @property
    def supported_languages(self) -> list[str]:
        return [self._language]
    
    @property
    def default_language(self) -> str:
        return self._language
        
    async def async_get_tts_audio(self, message: str, language: str, options: dict) -> TtsAudioType:
        # Možnost přepsat nastavení v rámci volání služby
        voice_id = options.get("voice", self._voice_id)
        # Sonic-3 se v API často volá 'sonic-multilingual' nebo 'sonic-3'
        model = options.get("model", "sonic-3") 
        speed = options.get("speed", self._speed)
        
        try:
            # Konstrukce nastavení hlasu a rychlosti
            # Použijeme typ 'Any', abychom obešli striktní kontrolu Pylance, 
            # protože __experimental_controls nemusí být v definici typu.
            voice_settings: Any = {
                "mode": "id", 
                "id": voice_id,
                "__experimental_controls": {"speed": speed}
            }

            audio_iter = self._client.tts.bytes(
                model_id=model,
                transcript=message,
                voice=voice_settings,
                language=self._language,
                output_format={"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100},
            )
            
            bytes_combined = b""
            async for chunk in audio_iter:
                bytes_combined += chunk
            return "wav", bytes_combined
            
        except ApiError as exc:
            raise HomeAssistantError(f"Cartesia API Error: {exc}") from exc
        except Exception as exc:
            raise HomeAssistantError(f"Unexpected Error: {exc}") from exc

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    # Načtení klienta z runtime_data
    data = getattr(config_entry, "runtime_data")
    
    # Načtení nastavení z config entry
    api_key = config_entry.data[CONF_API_KEY]
    name = config_entry.data.get("name", "Cartesia TTS")
    language = config_entry.data.get("language", "en")
    voice_id = config_entry.data.get("voice", "")
    speed = config_entry.data.get("speed", 1.0)
    
    unique_id = config_entry.entry_id
    
    # --- Načtení seznamu hlasů pro atributy entity ---
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    voices = []
    
    # 1. Zkusíme cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if cache.get("api_key") == api_key:
                    all_voices = cache.get("voices", [])
                    for v in all_voices:
                        langs = v["language"] if isinstance(v["language"], list) else [v["language"]]
                        if language in langs or "multilingual" in v.get("mode", ""):
                            voices.append(Voice(v["id"], v["name"]))
        except:
            pass
    
    # 2. Pokud cache selhala nebo je prázdná, zkusíme API
    if not voices:
        try:
            voices_pager = await data.client.voices.list()
            all_voices = [v async for v in voices_pager]
            
            for v in all_voices:
                langs = getattr(v, "language", [])
                if isinstance(langs, str):
                    langs = [langs]
                mode = getattr(v, "mode", "")
                
                if language in langs or "multilingual" in mode:
                    voices.append(Voice(getattr(v, 'id'), getattr(v, 'name')))
        except Exception:
            # Fallback při chybě
            voices.append(Voice(voice_id, "Unknown Voice"))

    # Přidání entity
    async_add_entities([
        CartesiaTTSEntity(
            client=data.client, 
            voices=voices, 
            voice_id=voice_id, 
            unique_id=unique_id, 
            language=language, 
            name=name, 
            speed=speed
        )
    ])
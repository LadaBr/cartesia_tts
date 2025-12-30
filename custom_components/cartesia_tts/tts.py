from typing import Any
from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
from homeassistant.components.tts import TextToSpeechEntity, TtsAudioType, Voice
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import os
import json
import io
import wave
from .const import VOICES_CACHE_FILE

# Nastavení ticha na začátku (v sekundách)
# 0.3s (300ms) je obvykle ideální pro ESP32
PRE_ROLL_SILENCE = 0.3
SAMPLE_RATE = 48000
CHANNELS = 1
WIDTH = 2  # 16-bit = 2 bajty

class CartesiaTTSEntity(TextToSpeechEntity):
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
        voice_id = options.get("voice", self._voice_id)
        model = options.get("model", "sonic-multilingual") 
        speed = options.get("speed", self._speed)
        
        try:
            voice_settings: Any = {
                "mode": "id", 
                "id": voice_id,
                "__experimental_controls": {"speed": speed}
            }

            # 1. Požádáme o RAW data (bez WAV hlavičky), abychom mohli manipulovat s bajty
            audio_iter = self._client.tts.bytes(
                model_id=model,
                transcript=message,
                voice=voice_settings,
                language=self._language,
                output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
            )
            
            # 2. Stáhneme všechna data hlasu
            raw_speech = b""
            async for chunk in audio_iter:
                raw_speech += chunk

            # 3. Vygenerujeme ticho na začátek
            # Počet bajtů = vzorkovací frekvence * délka ticha * kanály * bitová hloubka
            silence_bytes_count = int(SAMPLE_RATE * PRE_ROLL_SILENCE * CHANNELS * WIDTH)
            silence_data = b'\x00' * silence_bytes_count

            # 4. Spojíme Ticho + Hlas
            final_raw_data = silence_data + raw_speech

            # 5. Zabalíme to do WAV kontejneru (Home Assistant potřebuje hlavičku)
            # Vytvoříme soubor v paměti
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(final_raw_data)
            
            return "wav", buffer.getvalue()
            
        except ApiError as exc:
            raise HomeAssistantError(f"Cartesia API Error: {exc}") from exc
        except Exception as exc:
            raise HomeAssistantError(f"Unexpected Error: {exc}") from exc

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    data = getattr(config_entry, "runtime_data")
    
    api_key = config_entry.data[CONF_API_KEY]
    name = config_entry.data.get("name", "Cartesia TTS")
    language = config_entry.data.get("language", "en")
    voice_id = config_entry.data.get("voice", "")
    speed = config_entry.data.get("speed", 1.0)
    
    unique_id = config_entry.entry_id
    
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    voices = []
    
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
            voices.append(Voice(voice_id, "Unknown Voice"))

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
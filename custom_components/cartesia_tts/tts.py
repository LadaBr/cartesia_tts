from typing import Any
import os
import json
import io
import wave
import logging

from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError

from homeassistant.components.tts import (
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import VOICES_CACHE_FILE

_LOGGER = logging.getLogger(__name__)

# Nastavení ticha pro ESP32 satelity
PRE_ROLL_SILENCE = 0.3
SAMPLE_RATE = 44100
CHANNELS = 1
WIDTH = 2

class CartesiaTTSEntity(TextToSpeechEntity):
    """Implementace Cartesia TTS entity."""

    def __init__(self, client: AsyncCartesia, voices_list: list[Voice], voice_id: str, unique_id: str, language: str, name: str, speed: float = 1.0):
        self._client = client
        self._voices_list = voices_list # Seznam objektů Voice
        self._voice_id = voice_id
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

    @property
    def supported_options(self) -> list[str]:
        """Seznam podporovaných voleb pro tts.speak."""
        return ["voice", "speed", "model"]

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        """Tato metoda je KLÍČOVÁ pro Voice Assistanta. 
        Vrací seznam hlasů, které Pipeline může použít.
        """
        if language != self._language:
            return None
        return self._voices_list

    async def async_get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        """Generování audia s tichem na začátku."""
        voice_id = options.get("voice", self._voice_id)
        speed = options.get("speed", self._speed)
        model = options.get("model", "sonic-3")

        try:
            # Pylance fix pro experimentální parametry
            voice_settings: Any = {
                "mode": "id",
                "id": voice_id,
                "__experimental_controls": {"speed": float(speed)}
            }

            audio_iter = self._client.tts.bytes(
                model_id=model,
                transcript=message,
                voice=voice_settings,
                language=self._language,
                output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
            )

            raw_speech = b""
            async for chunk in audio_iter:
                raw_speech += chunk

            # Vložení ticha pro ESP32 (Wake-up delay)
            silence_bytes_count = int(SAMPLE_RATE * PRE_ROLL_SILENCE * CHANNELS * WIDTH)
            silence_data = b'\x00' * silence_bytes_count
            final_raw_data = silence_data + raw_speech

            # Zabalení do WAV
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(final_raw_data)

            return "wav", buffer.getvalue()

        except ApiError as exc:
            _LOGGER.error("Cartesia API Error: %s", exc)
            return None, None
        except Exception as exc:
            _LOGGER.error("Unexpected Error in Cartesia TTS: %s", exc)
            return None, None

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Nastavení entity při startu integrace."""
    data = getattr(config_entry, "runtime_data")
    
    api_key = config_entry.data[CONF_API_KEY]
    name = config_entry.data.get("name", "Cartesia TTS")
    language = config_entry.data.get("language", "cs")
    voice_id = config_entry.data.get("voice")
    speed = config_entry.data.get("speed", 1.0)
    
    # Načtení hlasů pro Pipeline
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    voices_for_entity = []

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if cache.get("api_key") == api_key:
                    for v in cache.get("voices", []):
                        v_langs = v["language"] if isinstance(v["language"], list) else [v["language"]]
                        if language in v_langs or "multilingual" in v.get("mode", ""):
                            # Tady vytváříme objekty Voice, které Pipeline vyžaduje
                            voices_for_entity.append(Voice(v["id"], v["name"]))
        except Exception as e:
            _LOGGER.error("Chyba při načítání cache hlasů: %s", e)

    # Pokud cache selže, přidáme aspoň ten jeden nakonfigurovaný
    if not voices_for_entity:
        voices_for_entity.append(Voice(voice_id, name))

    async_add_entities([
        CartesiaTTSEntity(
            client=data.client,
            voices_list=voices_for_entity,
            voice_id=voice_id,
            unique_id=config_entry.entry_id,
            language=language,
            name=name,
            speed=speed
        )
    ])
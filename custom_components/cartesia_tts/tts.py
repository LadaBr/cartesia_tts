from typing import Any, AsyncGenerator
from dataclasses import dataclass
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

@dataclass
class TTSAudioRequest:
    """Request for streaming TTS audio."""
    language: str
    options: dict[str, Any]
    message_gen: AsyncGenerator[str, None]

@dataclass
class TTSAudioResponse:
    """Response with streaming TTS audio."""
    extension: str
    data_gen: AsyncGenerator[bytes, None]

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

    def _get_voice_settings(self, options: dict[str, Any]) -> tuple[Any, str, float]:
        """Prepare voice settings for API call."""
        voice_id = options.get("voice", self._voice_id)
        speed = options.get("speed", self._speed)
        model = options.get("model", "sonic-3")
        
        voice_settings: Any = {
            "mode": "id",
            "id": voice_id,
            "__experimental_controls": {"speed": float(speed)}
        }
        
        return voice_settings, model, speed

    def _create_silence_wav(self) -> bytes:
        """Create pre-roll silence for ESP32 satellite wake-up."""
        silence_bytes_count = int(SAMPLE_RATE * PRE_ROLL_SILENCE * CHANNELS * WIDTH)
        silence_data = b'\x00' * silence_bytes_count
        
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(silence_data)
        
        return buffer.getvalue()

    def _wrap_raw_audio_to_wav(self, raw_audio: bytes) -> bytes:
        """Wrap raw PCM audio data into WAV container."""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(raw_audio)
        
        return buffer.getvalue()

    async def async_get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        """Generování audia - používá streaming a sbírá výsledek."""
        _LOGGER.info("TTS Request - Message: '%s', Language: %s, Options: %s", message[:50], language, options)
        
        try:
            # Create single-message generator
            async def message_gen() -> AsyncGenerator[str, None]:
                yield message
            
            # Use streaming method
            request = TTSAudioRequest(
                language=language,
                options=options,
                message_gen=message_gen()
            )
            
            response = await self.async_stream_tts_audio(request)
            
            # Collect all audio chunks
            audio_data = b""
            chunk_count = 0
            async for chunk in response.data_gen:
                audio_data += chunk
                chunk_count += 1
            
            _LOGGER.info("Collected %d audio chunks, total bytes: %d", chunk_count, len(audio_data))
            _LOGGER.info("TTS audio generated successfully")
            
            return response.extension, audio_data

        except Exception as exc:
            _LOGGER.error("Error in TTS generation: %s", exc, exc_info=True)
            return None, None

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        """Stream TTS audio with real-time generation from LLM text chunks."""
        voice_settings, model, _ = self._get_voice_settings(request.options)
        
        _LOGGER.debug("Starting streaming TTS for language: %s", request.language)

        async def audio_generator() -> AsyncGenerator[bytes, None]:
            """Generate audio chunks as they arrive."""
            try:
                # Collect full message from LLM stream
                full_message = ""
                async for text_chunk in request.message_gen:
                    full_message += text_chunk
                
                if not full_message.strip():
                    _LOGGER.warning("Empty message received in streaming TTS")
                    return

                _LOGGER.info("Streaming TTS for message: '%s...'", full_message[:50])

                # Stream audio from Cartesia
                audio_iter = self._client.tts.bytes(
                    model_id=model,
                    transcript=full_message,
                    voice=voice_settings,
                    language=request.language,
                    output_format={"container": "wav", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
                )

                # Stream audio chunks as they arrive
                async for audio_chunk in audio_iter:
                    if audio_chunk:
                        yield audio_chunk

            except ApiError as exc:
                _LOGGER.error("Cartesia API Error in streaming: %s", exc)
                raise HomeAssistantError(f"Cartesia streaming error: {exc}") from exc
            except Exception as exc:
                _LOGGER.error("Unexpected error in streaming TTS: %s", exc)
                raise HomeAssistantError(f"Streaming TTS error: {exc}") from exc

        return TTSAudioResponse(
            extension="wav",
            data_gen=audio_generator()
        )

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Nastavení entity při startu integrace."""
    data = getattr(config_entry, "runtime_data")
    
    api_key = config_entry.data[CONF_API_KEY]
    name = config_entry.data.get("name", "Cartesia TTS")
    language = config_entry.data.get("language", "cs")
    voice_id = config_entry.data.get("voice", "")
    speed = config_entry.data.get("speed", 1.0)
    
    # Načtení hlasů pro Pipeline
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    voices_for_entity = []

    if os.path.exists(cache_file):
        try:
            def _read_cache():
                with open(cache_file, "r") as f:
                    return json.load(f)
            
            cache = await hass.async_add_executor_job(_read_cache)
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
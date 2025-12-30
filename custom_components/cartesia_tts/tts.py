from cartesia import AsyncCartesia
from cartesia.core.api_error import ApiError
from homeassistant.components.tts import TextToSpeechEntity, TTSAudioRequest, TTSAudioResponse, TtsAudioType, Voice
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

class CartesiaTTSEntity(TextToSpeechEntity):
    _attr_supported_options = ["voice", "model"]
    _attr_supported_languages = ["cs", "en", "de", "es", "fr", "it", "pl", "pt", "zh", "ja"]
    
    def __init__(self, client: AsyncCartesia, voices, default_voice_id: str, entry_id: str):
        self._client = client
        self._default_voice_id = default_voice_id
        self._voices = [Voice(v.id, v.name) for v in voices]
        self._attr_name = "Cartesia TTS"
        self._attr_unique_id = entry_id
        
    async def async_get_tts_audio(self, message: str, language: str, options: dict) -> TtsAudioType:
        voice_id = options.get("voice", self._default_voice_id)
        model = options.get("model", "sonic-3")
        try:
            audio_iter = self._client.tts.bytes(
                model_id=model,
                transcript=message,
                voice={"mode": "id", "id": voice_id},
                language=language,
                output_format={"container": "mp3", "sample_rate": 44100},
            )
            bytes_combined = b""
            async for chunk in audio_iter:
                bytes_combined += chunk
            return "mp3", bytes_combined
        except ApiError as exc:
            raise HomeAssistantError(exc) from exc
    
    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        return TTSAudioResponse("mp3", self._process_tts_stream(request))
    
    async def _process_tts_stream(self, request: TTSAudioRequest):
        text = ""
        async for chunk in request.message_gen:
            text += chunk
        voice_id = request.options.get("voice", self._default_voice_id)
        model = request.options.get("model", "sonic-3")
        language = request.language or "en"
        try:
            async for chunk in self._client.tts.bytes(
                model_id=model,
                transcript=text,
                voice={"mode": "id", "id": voice_id},
                language=language,
                output_format={"container": "mp3", "sample_rate": 44100},
            ):
                yield chunk
        except ApiError as exc:
            raise HomeAssistantError(exc) from exc

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    data = config_entry.runtime_data
    voices = [v async for v in data.client.voices.list()]
    async_add_entities([CartesiaTTSEntity(data.client, voices, config_entry.options.get("voice", ""), config_entry.entry_id)])
# Cartesia TTS Home Assistant Integration

This is a custom Home Assistant integration for Cartesia TTS.

## Features

- High-quality TTS using Cartesia AI
- Support for multiple voices and models
- Streaming audio support
- Multiple language support (cs, en, de, es, fr, it, pl, pt, zh, ja)
- Voice caching to reduce API calls
- Language-based voice filtering
- Refresh voices service

## Installation

1. Copy the `custom_components/cartesia_tts` directory to your Home Assistant `config/custom_components/` directory.

2. Restart Home Assistant.

3. Go to Settings > Devices & Services > Add Integration > Cartesia TTS.

4. Enter your Cartesia API key and select language.

## Configuration

- **API Key**: Get from https://play.cartesia.ai/
- **Language**: Select language to filter voices
- **Voice**: Select from filtered voices
- **Model**: Choose sonic-3 or sonic-2

## Services

- **cartesia_tts.refresh_voices**: Refresh the cached voices list. Call this service to update voices after adding new ones in Cartesia.

## Usage

Use the TTS entity in automations or UI for announcements.

Voices are cached locally to reduce API calls. Use the refresh service to update the cache.

- Cartesia API key from https://play.cartesia.ai/

- Home Assistant with custom components support.
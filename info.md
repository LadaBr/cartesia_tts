# Cartesia TTS

Custom Home Assistant integration for Cartesia Text-to-Speech.

## Features

- High-quality TTS using Cartesia AI
- Support for multiple voices and models
- Streaming audio support
- Multiple language support (cs, en, de, es, fr, it, pl, pt, zh, ja)

## Installation

1. Install via HACS (search for "Cartesia TTS") or manually copy `custom_components/cartesia_tts` to your HA config directory.
2. Restart HA.
3. Add integration in Settings > Devices & Services.
4. Enter your Cartesia API key.

## Configuration

- **API Key**: Get from https://play.cartesia.ai/
- **Voice**: Select from available voices
- **Model**: Choose sonic-3 or sonic-2
- **Language**: Supported languages listed above

## Usage

Use the TTS entity in automations or UI for announcements.
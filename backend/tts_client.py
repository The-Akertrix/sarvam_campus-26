"""Sarvam AI Bulbul text-to-speech adapter."""

from __future__ import annotations

import asyncio
import base64
import binascii

from backend.config import settings


class SarvamTTSClient:
    """Calls the official `sarvamai` SDK and returns decoded WAV bytes."""

    def __init__(self) -> None:
        self.api_key = settings.sarvam_api_key
        self.model = settings.sarvam_model
        self.speaker = settings.sarvam_speaker

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def synthesize(self, text: str, language_code: str) -> bytes:
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured. Add it to .env to synthesize audio.")
        if len(text) > 2500:
            raise ValueError("Sarvam Bulbul v3 accepts up to 2,500 characters per request.")

        def _convert() -> bytes:
            try:
                from sarvamai import SarvamAI
            except ImportError as exc:
                raise RuntimeError("Install the sarvamai package to enable speech synthesis.") from exc

            client = SarvamAI(api_subscription_key=self.api_key)
            response = client.text_to_speech.convert(
                text=text,
                language_code=language_code,
                model=self.model,
                speaker=self.speaker,
                output_audio_codec="wav",
            )
            audios = response.get("audios") if isinstance(response, dict) else response.audios
            if not audios:
                raise RuntimeError("Sarvam returned an empty audio response.")
            encoded = "".join(audios)
            try:
                return base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError("Sarvam returned invalid base64 audio data.") from exc

        return await asyncio.to_thread(_convert)

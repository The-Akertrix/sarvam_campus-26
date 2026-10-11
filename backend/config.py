"""Environment-backed configuration for the local prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

LANGUAGE_CATALOG: dict[str, dict[str, str]] = {
    "bn-IN": {"name": "Bengali", "native_name": "বাংলা"},
    "hi-IN": {"name": "Hindi", "native_name": "हिन्दी"},
    "en-IN": {"name": "English", "native_name": "English"},
    "ta-IN": {"name": "Tamil", "native_name": "தமிழ்"},
    "te-IN": {"name": "Telugu", "native_name": "తెలుగు"},
    "mr-IN": {"name": "Marathi", "native_name": "मराठी"},
    "gu-IN": {"name": "Gujarati", "native_name": "ગુજરાતી"},
    "kn-IN": {"name": "Kannada", "native_name": "ಕನ್ನಡ"},
    "ml-IN": {"name": "Malayalam", "native_name": "മലയാളം"},
    "pa-IN": {"name": "Punjabi", "native_name": "ਪੰਜਾਬੀ"},
    "od-IN": {"name": "Odia", "native_name": "ଓଡ଼ିଆ"},
}


def _language_sequence() -> tuple[str, ...]:
    raw = os.getenv("PREFERRED_LANGUAGES", "bn-IN,hi-IN,en-IN")
    codes = tuple(code.strip() for code in raw.split(",") if code.strip())
    invalid = [code for code in codes if code not in LANGUAGE_CATALOG]
    if invalid:
        raise ValueError(f"Unsupported PREFERRED_LANGUAGES code(s): {', '.join(invalid)}")
    if not codes:
        raise ValueError("PREFERRED_LANGUAGES must contain at least one language code")
    return codes


@dataclass(frozen=True)
class Settings:
    station_code: str = os.getenv("STATION_CODE", "HWH")
    station_name: str = os.getenv("STATION_NAME", "Howrah Junction")
    timezone: str = os.getenv("STATION_TIMEZONE", "Asia/Kolkata")
    sarvam_api_key: str | None = os.getenv("SARVAM_API_KEY") or None
    sarvam_model: str = os.getenv("SARVAM_MODEL", "bulbul:v3")
    sarvam_speaker: str = os.getenv("SARVAM_SPEAKER", "shubh")
    poll_interval_seconds: float = float(os.getenv("POLL_INTERVAL_SECONDS", "3"))
    preferred_languages: tuple[str, ...] = _language_sequence()


settings = Settings()

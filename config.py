"""
config.py
---------
Centralized configuration. All API keys and tunables are read from
environment variables (optionally loaded from a local .env file if
python-dotenv is installed) so no secrets live in source code.

Set these in your shell, or create a `.env` file next to assistant.py:

    OPENWEATHER_API_KEY=your_openweathermap_key
    NEWSAPI_KEY=your_newsapi_key
    ASSISTANT_WAKE_WORD=assistant
    ASSISTANT_DEFAULT_LOCATION=Jaipur
    ASSISTANT_UNITS=metric
"""

from __future__ import annotations

import os

# Load a .env file if python-dotenv is available. Purely optional — the app
# works fine with real environment variables and no .env file at all.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# -- API keys -----------------------------------------------------------
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

# -- Assistant behavior ---------------------------------------------------
WAKE_WORD = os.environ.get("ASSISTANT_WAKE_WORD", "assistant").strip().lower()
DEFAULT_LOCATION = os.environ.get("ASSISTANT_DEFAULT_LOCATION", "Jaipur")
UNITS = os.environ.get("ASSISTANT_UNITS", "metric")  # "metric" or "imperial"
NEWS_COUNTRY = os.environ.get("ASSISTANT_NEWS_COUNTRY", "us")

# -- Reminders --------------------------------------------------------------
REMINDER_POLL_INTERVAL_SECONDS = int(os.environ.get("ASSISTANT_REMINDER_POLL_SECONDS", "15"))

# -- Speech -----------------------------------------------------------------
TTS_RATE = int(os.environ.get("ASSISTANT_TTS_RATE", "180"))
REQUIRE_WAKE_WORD = _get_bool("ASSISTANT_REQUIRE_WAKE_WORD", True)


def require_openweather_key() -> str:
    if not OPENWEATHER_API_KEY:
        raise RuntimeError(
            "OPENWEATHER_API_KEY is not set. Get a free key at "
            "https://openweathermap.org/api and export it as an environment variable."
        )
    return OPENWEATHER_API_KEY


def require_newsapi_key() -> str:
    if not NEWSAPI_KEY:
        raise RuntimeError(
            "NEWSAPI_KEY is not set. Get a free key at https://newsapi.org "
            "and export it as an environment variable."
        )
    return NEWSAPI_KEY

"""
weather.py
----------
Fetches current conditions from the OpenWeatherMap API. Requires
OPENWEATHER_API_KEY to be set (see modules/config.py). Get a free key at
https://openweathermap.org/api.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from . import config

logger = logging.getLogger("assistant.weather")

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
REQUEST_TIMEOUT_SECONDS = 8


class WeatherError(Exception):
    """Raised when the weather service can't be reached or returns bad data."""


@dataclass
class WeatherReport:
    location: str
    description: str
    temp: float
    feels_like: float
    humidity: int
    wind_speed: float
    units: str  # "metric" or "imperial"

    def spoken_summary(self) -> str:
        unit_symbol = "C" if self.units == "metric" else "F"
        parts = [
            f"It's currently {self.description.lower()} in {self.location}, "
            f"about {round(self.temp)} degrees {unit_symbol}."
        ]
        if abs(self.feels_like - self.temp) >= 2:
            parts.append(f"It feels like {round(self.feels_like)} degrees {unit_symbol}.")
        if self.humidity >= 70:
            parts.append(f"Humidity is high, at {self.humidity} percent.")
        return " ".join(parts)


def get_weather(location: str, units: Optional[str] = None) -> WeatherReport:
    """
    Look up current weather for a free-text location string, e.g.
    "Jaipur", "New York", "Paris,FR". `units` is "metric" (Celsius) or
    "imperial" (Fahrenheit); defaults to config.UNITS.
    """
    if not location or not location.strip():
        raise WeatherError("No location provided.")

    units = units or config.UNITS
    try:
        api_key = config.require_openweather_key()
    except RuntimeError as exc:
        raise WeatherError(str(exc)) from exc

    params = {
        "q": location.strip(),
        "appid": api_key,
        "units": units,
    }

    try:
        response = requests.get(CURRENT_WEATHER_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        logger.exception("Weather request failed")
        raise WeatherError(f"Could not reach the weather service: {exc}") from exc

    if response.status_code == 404:
        raise WeatherError(f"I couldn't find a location called '{location}'.")
    if response.status_code == 401:
        raise WeatherError("The OpenWeatherMap API key is invalid or not yet activated.")

    try:
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise WeatherError(f"Weather service returned an error: {exc}") from exc
    except ValueError as exc:
        raise WeatherError("Weather service returned an unreadable response.") from exc

    try:
        weather_list = data["weather"]
        main = data["main"]
        wind = data.get("wind", {})
        display_location = f"{data['name']}, {data['sys']['country']}" if data.get("sys", {}).get("country") else data.get("name", location)

        return WeatherReport(
            location=display_location,
            description=weather_list[0]["description"],
            temp=float(main["temp"]),
            feels_like=float(main["feels_like"]),
            humidity=int(main["humidity"]),
            wind_speed=float(wind.get("speed", 0.0)),
            units=units,
        )
    except (KeyError, IndexError, ValueError) as exc:
        raise WeatherError("Weather service returned unexpected data format.") from exc

import os
import time
import logging
from typing import Optional, Dict, Any

import requests

log = logging.getLogger(__name__)

# Simple in-process cache so we don't hammer the API:
_WEATHER_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "data": None,
}

# Defaults: demo location (override with BUSINESS_LAT/BUSINESS_LON/BUSINESS_CITY)
DEFAULT_LAT = float(os.getenv("BUSINESS_LAT", "28.5384"))   # demo location (central Florida)
DEFAULT_LON = float(os.getenv("BUSINESS_LON", "-81.3789"))  # demo location
DEFAULT_CITY = os.getenv("BUSINESS_CITY", "Sunnyvale")
DEFAULT_REGION = os.getenv("BUSINESS_REGION", "FL")


def _fetch_weather_raw(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Use Open-Meteo (no API key required) to get basic current weather.
    Docs: https://open-meteo.com/
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current_weather=true"
    )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("current_weather")
    except Exception as e:
        log.warning("[weather_client] Failed to fetch weather: %s", e)
        return None


def get_current_weather(force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Returns a dict like:
    {
      "temperature_f": 72.1,
      "windspeed": 5.3,
      "winddirection": 180,
      "is_day": 1,
      "weathercode": 1,
    }
    or None if it fails.
    """
    global _WEATHER_CACHE
    now = time.time()

    # Cache for 10 min
    if not force_refresh and _WEATHER_CACHE["data"] and now - _WEATHER_CACHE["ts"] < 600:
        return _WEATHER_CACHE["data"]

    raw = _fetch_weather_raw(DEFAULT_LAT, DEFAULT_LON)
    if not raw:
        return None

    temp_c = raw.get("temperature")
    if temp_c is None:
        return None

    temp_f = temp_c * 9.0 / 5.0 + 32.0

    result = {
        "temperature_f": round(temp_f, 1),
        "windspeed": raw.get("windspeed"),
        "winddirection": raw.get("winddirection"),
        "is_day": raw.get("is_day"),
        "weathercode": raw.get("weathercode"),
        "city": DEFAULT_CITY,
        "region": DEFAULT_REGION,
    }

    _WEATHER_CACHE = {"ts": now, "data": result}
    return result


def describe_weather_for_prompt() -> str:
    """
    Return a short, LLM-friendly description string for use in caption prompts.
    Example:
      "Current weather in Sunnyvale, FL: 68°F, mild and comfortable. Early December – not peak summer heat."
    """
    data = get_current_weather()
    if not data:
        return ""

    temp_f = data["temperature_f"]
    city = data["city"]
    region = data["region"]

    # Rough, human-ish label:
    if temp_f >= 90:
        feel = "very hot and intense"
    elif temp_f >= 82:
        feel = "hot and humid"
    elif temp_f >= 75:
        feel = "warm and comfortable"
    elif temp_f >= 68:
        feel = "mild and pleasant"
    elif temp_f >= 60:
        feel = "cool for a Florida day"
    else:
        feel = "unusually cool for Florida"

    return (
        f"Current weather in {city}, {region}: about {temp_f}°F, {feel}. "
        "Adjust pool talk to match this actual weather, not generic summer vibes."
    )


if __name__ == "__main__":
    print(describe_weather_for_prompt())

"""
weather_service.py
------------------
Fetches a 16-day daily forecast from OpenWeatherMap for the farm centroid
and returns structured data ready for the PDF generator.

API used:
  GET https://api.openweathermap.org/data/2.5/forecast/daily
      ?lat=<lat>&lon=<lon>&units=metric&cnt=16&appid=<key>
"""

import logging
import requests
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

OWM_KEY = '8fe0250d67259f443d53736d749778b9'
OWM_URL = 'https://api.openweathermap.org/data/2.5/forecast/daily'


def fetch_weather(lat: float, lon: float, days: int = 16) -> dict:
    """
    Returns:
      {
        "city":    str,
        "country": str,
        "days": [
          {
            "date":       "20 Apr",
            "temp_max":   float,   # °C
            "temp_min":   float,   # °C
            "humidity":   int,     # %
            "wind_speed": float,   # m/s
            "wind_dir":   str,     # "N", "NE", etc.
            "description": str,   # "clear sky"
            "icon":        str,   # OWM icon code e.g. "01d"
          },
          ...
        ],
        "error": str | None,
      }
    """
    result = {"city": "", "country": "", "days": [], "error": None}

    try:
        resp = requests.get(
            OWM_URL,
            params={
                "lat":   lat,
                "lon":   lon,
                "units": "metric",
                "cnt":   days,
                "appid": OWM_KEY,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            result["error"] = f"OWM {resp.status_code}: {resp.text[:200]}"
            return result

        data = resp.json()
        result["city"]    = data.get("city", {}).get("name", "")
        result["country"] = data.get("city", {}).get("country", "")

        for entry in data.get("list", []):
            dt   = datetime.utcfromtimestamp(entry["dt"])
            temp = entry.get("temp", {})
            wind = entry.get("speed", 0)
            deg  = entry.get("deg", 0)

            result["days"].append({
                "date":        dt.strftime("%d %b").lstrip("0").replace(" 0", " "),
                "temp_max":    round(temp.get("max", 0), 1),
                "temp_min":    round(temp.get("min", 0), 1),
                "humidity":    entry.get("humidity", 0),
                "wind_speed":  round(wind, 1),
                "wind_dir":    _deg_to_compass(deg),
                "description": entry.get("weather", [{}])[0].get("description", "").title(),
                "icon":        entry.get("weather", [{}])[0].get("icon", "01d"),
            })

        logger.info(f"Weather fetched for ({lat},{lon}): {len(result['days'])} days, city={result['city']}")

    except Exception as e:
        logger.error(f"fetch_weather failed: {e}", exc_info=True)
        result["error"] = str(e)

    return result


def _deg_to_compass(deg: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[int((deg + 11.25) / 22.5) % 16]

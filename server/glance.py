"""Ambient data — weather, Twitch."""

import json
import os
import time
import urllib.request
from server.config import HERMES_HOME
# =============================================================================
# Glance data — weather, Twitch streams, world clock config
# Transferred from glance.vladislavstoyanov.com (glanceapp/glance)
# =============================================================================

# Veliko Tarnovo coordinates (from Open-Meteo geocoding)
_GLANCE_WEATHER_LAT = 43.0812
_GLANCE_WEATHER_LON = 25.6347
_GLANCE_WEATHER_TZ = "Europe/Sofia"

# Twitch GQL — same public endpoint glance uses
_TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
_TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# Timezones for world clock (from glance config)
_GLANCE_TIMEZONES = [
    ("Europe/Sofia", "Sofia"),
    ("UTC", "UTC"),
    ("Europe/Rome", "Italy"),
    ("America/Los_Angeles", "US West"),
    ("America/New_York", "US East"),
    ("Asia/Singapore", "Singapore"),
    ("Australia/Sydney", "Australia"),
]

# Twitch channels to monitor (from glance config)
_GLANCE_TWITCH_CHANNELS = [
    "shuncrone", "ladyauroratv", "wejil", "biotrextv", "mordant_cassie",
    "yuca_", "shinosaito", "colt_gunner_mh", "maximilian_dood", "justtus23",
    "yvreux", "hidesashi", "beringr", "garucabra", "6thquill",
    "swaticus05", "captainkaleo", "kaizowario", "peeboz", "vbgkenji", "nzknbr",
]

# Cache
_weather_cache = {"data": None, "ts": 0}
_twitch_cache = {"data": None, "ts": 0}
_WEATHER_CACHE_TTL = 3600    # 1 hour
_TWITCH_CACHE_TTL = 120      # 2 minutes

# WMO weather code → human-readable label
_WMO_CODES = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    80: "Rain Showers", 81: "Moderate Rain Showers", 82: "Heavy Rain Showers",
    95: "Thunderstorm", 96: "T-storm + Hail", 99: "Heavy T-storm + Hail",
}


def _fetch_weather():
    """Fetch current weather for Veliko Tarnovo from Open-Meteo (free, no key)."""
    global _weather_cache
    now = time.time()
    if _weather_cache["data"] is not None and (now - _weather_cache["ts"]) < _WEATHER_CACHE_TTL:
        return _weather_cache["data"]

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={_GLANCE_WEATHER_LAT}&longitude={_GLANCE_WEATHER_LON}"
            f"&current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m"
            f"&timezone={urllib.parse.quote(_GLANCE_WEATHER_TZ)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "MissionControl/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current", {})
        code = current.get("weather_code", 0)
        result = {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "weather_code": code,
            "weather_label": _WMO_CODES.get(code, f"Code {code}"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "location": "Veliko Tarnovo",
            "updated": now,
        }
        _weather_cache = {"data": result, "ts": now}
        return result
    except Exception:
        # Return stale cache if available
        if _weather_cache["data"] is not None:
            return _weather_cache["data"]
        return {"error": "weather fetch failed", "location": "Veliko Tarnovo"}


def _fetch_twitch_streams():
    """Fetch live status for configured Twitch channels via GQL (same approach as glance)."""
    global _twitch_cache
    now = time.time()
    if _twitch_cache["data"] is not None and (now - _twitch_cache["ts"]) < _TWITCH_CACHE_TTL:
        return _twitch_cache["data"]

    try:
        results = []
        # Fetch each channel; Twitch GQL supports batched queries but one-at-a-time is simpler
        for channel in _GLANCE_TWITCH_CHANNELS:
            try:
                info = _fetch_single_twitch_channel(channel)
                results.append(info)
            except Exception:
                results.append({"login": channel, "error": "fetch failed"})

        # Sort: live first, by viewers desc; then offline alphabetically
        live = [r for r in results if r.get("is_live")]
        offline = [r for r in results if not r.get("is_live")]
        live.sort(key=lambda r: -(r.get("viewers_count", 0)))
        offline.sort(key=lambda r: r.get("login", ""))
        sorted_results = live + offline

        data = {"channels": sorted_results, "live_count": len(live), "total": len(sorted_results), "updated": now}
        _twitch_cache = {"data": data, "ts": now}
        return data
    except Exception:
        if _twitch_cache["data"] is not None:
            return _twitch_cache["data"]
        return {"channels": [], "live_count": 0, "total": 0, "error": "twitch fetch failed"}


def _fetch_single_twitch_channel(login):
    """Fetch a single Twitch channel's live status via GQL persisted queries."""
    body = json.dumps([
        {
            "operationName": "ChannelShell",
            "variables": {"login": login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe"
                }
            }
        },
        {
            "operationName": "StreamMetadata",
            "variables": {"channelLogin": login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "676ee2f834ede42eb4514cdb432b3134fefc12590080c9a2c9bb44a2a4a63266"
                }
            }
        }
    ]).encode("utf-8")

    req = urllib.request.Request(
        _TWITCH_GQL_URL,
        data=body,
        headers={
            "Client-ID": _TWITCH_CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": "MissionControl/1.0",
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        ops = json.loads(resp.read().decode("utf-8"))

    result = {"login": login, "display_name": login, "is_live": False}

    if not isinstance(ops, list) or len(ops) < 1:
        return result

    # Parse ChannelShell (first operation)
    shell = ops[0].get("data", {})
    user = shell.get("userOrError", {})
    if user.get("__typename") == "User":
        result["display_name"] = user.get("displayName", login)
        result["avatar_url"] = user.get("profileImageURL", "")
        stream = user.get("stream")
        if stream is not None:
            result["is_live"] = True
            result["viewers_count"] = stream.get("viewersCount", 0)
            # Parse StreamMetadata (second operation) for title/category
            if len(ops) >= 2:
                meta = ops[1].get("data", {}).get("user")
                if meta:
                    if meta.get("lastBroadcast"):
                        result["title"] = meta["lastBroadcast"].get("title", "")
                    s = meta.get("stream")
                    if s:
                        result["started_at"] = s.get("createdAt", "")
                        g = s.get("game")
                        if g:
                            result["category"] = g.get("name", "")

    return result


def _get_glance_data():
    """Return combined glance data: timezones, weather, twitch."""
    return {
        "timezones": _GLANCE_TIMEZONES,
        "weather": _fetch_weather(),
        "twitch": _fetch_twitch_streams(),
    }


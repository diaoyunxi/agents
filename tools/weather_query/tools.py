"""天气查询：默认 Open-Meteo（免密钥），按城市名地理编码后取实时与预报。"""

from __future__ import annotations

import httpx

NAME = "weather_query"
DESCRIPTION = "查询天气：按城市名或经纬度获取当前天气与未来预报（Open-Meteo 免密钥）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "location": {"type": "string", "description": "城市名，如 北京 / London"},
        "latitude": {"type": "number", "description": "纬度（提供则跳过城市名解析）"},
        "longitude": {"type": "number", "description": "经度"},
        "forecast_days": {"type": "integer", "description": "预报天数，默认 3，最大 7"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
    },
    "required": [],
}

WEATHER_CODES = {
    0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨", 61: "小雨", 63: "中雨",
    65: "大雨", 66: "冻雨(小)", 67: "冻雨(大)", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "雪粒", 80: "阵雨(小)", 81: "阵雨(中)", 82: "阵雨(大)", 85: "阵雪",
    86: "阵雪(大)", 95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴大冰雹",
}


def _geocode(name: str, timeout: int) -> tuple[float, float, str] | None:
    try:
        resp = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": name, "count": 1, "language": "zh", "format": "json"},
                         timeout=timeout)
        results = (resp.json().get("results") or [])
        if not results:
            return None
        r = results[0]
        return r["latitude"], r["longitude"], f"{r.get('name', name)}（{r.get('admin1', '')} {r.get('country', '')}）"
    except httpx.HTTPError:
        return None


def _temp_unit() -> str:
    return "C"


def run(location: str = "", latitude: float | None = None, longitude: float | None = None,
        forecast_days: int = 3, timeout: int = 20) -> dict:
    forecast_days = max(1, min(int(forecast_days or 3), 7))
    timeout = max(5, min(int(timeout or 20), 60))

    place_label = ""
    if latitude is not None and longitude is not None:
        place_label = f"{latitude},{longitude}"
    else:
        if not location:
            return {"ok": False, "output": "请提供 location（城市名）或 latitude+longitude"}
        hit = _geocode(location, timeout)
        if not hit:
            return {"ok": False, "output": f"未能解析城市: {location}（请换个写法或给经纬度）"}
        latitude, longitude, place_label = hit

    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude, "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto", "forecast_days": forecast_days + 1,
            },
            timeout=timeout)
        if resp.status_code >= 400:
            return {"ok": False, "output": f"Open-Meteo HTTP {resp.status_code}"}
        data = resp.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"天气请求失败: {exc}"}

    cur = data.get("current", {})
    lines = [f"地点: {place_label}",
             f"当前: {WEATHER_CODES.get(cur.get('weather_code'), cur.get('weather_code'))} | "
             f"{cur.get('temperature_2m')}°C（体感 {cur.get('apparent_temperature')}°C） | "
             f"湿度 {cur.get('relative_humidity_2m')}% | 风速 {cur.get('wind_speed_10m')} km/h"]

    daily = data.get("daily", {})
    days = daily.get("time", [])

    def _at(key: str, i: int):
        arr = daily.get(key) or []
        return arr[i] if i < len(arr) else None

    for i, day in enumerate(days[:forecast_days]):
        code = _at("weather_code", i)
        hi = _at("temperature_2m_max", i)
        lo = _at("temperature_2m_min", i)
        pop = _at("precipitation_probability_max", i)
        lines.append(f"{day}: {WEATHER_CODES.get(code, '')} {lo}~{hi}°C | 降水概率 {pop}%")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]

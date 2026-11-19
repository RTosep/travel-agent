"""Weather tool: Amap geocoding + Amap weather."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..models import CurrentWeather, DailyWeather, WeatherReport
from ..trace import get_logger
from .amap import amap_call, clean_str, geocode, resolve_key
from .base import Tool

log = get_logger("tools.weather")

WEATHER_PATH = "/v3/weather/weatherInfo"
USER_AGENT = "travel-agent-handrolled/0.1"


class WeatherArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str = Field(
        min_length=1,
        description="城市名称，中文或英文均可，例如“北京”“上海”“成都”",
    )


def build_weather_tool() -> Tool:
    return Tool(
        name="get_weather",
        description=(
            "查询城市当前天气和未来 4 天预报。用于判断穿衣、雨季、户外活动安排和雨天备选方案。"
        ),
        parameters=WeatherArgs.model_json_schema(),
        handler=lambda args: get_weather(WeatherArgs.model_validate(args).city),
    )


def get_weather(
    city: str,
    *,
    client: httpx.Client | None = None,
    amap_key: str | None = None,
) -> WeatherReport | dict[str, Any]:
    city = city.strip()
    log.debug("get_weather 入参：city=%r", city)

    if not city:
        log.warning("city 为空")
        return {"error": "城市不能为空。"}

    key, err = resolve_key(amap_key)
    if err:
        return {"error": err}

    owns_client = client is None
    http = client or httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT})

    try:
        log.debug("第 1 步：高德地理编码，把城市名转成经纬度和 adcode")
        place = geocode(city, key=key, client=http)
        if isinstance(place, dict):
            return {"error": f"定位失败：{place['error']}"}

        city_code = place.adcode or place.name or city
        log.debug("第 2 步：高德实况天气 city=%s", city_code)
        live_data, err = amap_call(
            http,
            WEATHER_PATH,
            {"city": city_code, "extensions": "base"},
            key,
        )
        if err:
            return {"error": err}

        log.debug("第 3 步：高德 4 天预报 city=%s", city_code)
        forecast_data, err = amap_call(
            http,
            WEATHER_PATH,
            {"city": city_code, "extensions": "all"},
            key,
        )
        if err:
            return {"error": err}

        current = _current_weather(live_data)
        daily = _daily_forecast(forecast_data)
        log.debug(
            "解析完成：当前天气=%s，未来 %d 天", current.weather if current else "无", len(daily)
        )

        return WeatherReport(
            location=place,
            current=current,
            daily=daily,
            weather_source="高德地图",
            geocode_source="高德地图",
        )
    finally:
        if owns_client:
            http.close()


def _current_weather(data: dict[str, Any]) -> CurrentWeather | None:
    lives = data.get("lives")
    if not isinstance(lives, list) or not lives:
        return None

    live = lives[0]
    if not isinstance(live, dict):
        return None

    return CurrentWeather(
        time=clean_str(live.get("reporttime")),
        weather=clean_str(live.get("weather")),
        temperature_c=_to_float(live.get("temperature")),
        humidity=clean_str(live.get("humidity")),
        wind_direction=clean_str(live.get("winddirection")),
        wind_power=clean_str(live.get("windpower")),
    )


def _daily_forecast(data: dict[str, Any]) -> list[DailyWeather]:
    forecasts = data.get("forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        return []

    first = forecasts[0]
    if not isinstance(first, dict):
        return []

    casts = first.get("casts")
    if not isinstance(casts, list):
        return []

    rows: list[DailyWeather] = []
    for cast in casts:
        if not isinstance(cast, dict):
            continue
        day = clean_str(cast.get("dayweather"))
        night = clean_str(cast.get("nightweather"))
        weather = " / ".join(part for part in (day, night) if part) or None
        rows.append(
            DailyWeather(
                date=clean_str(cast.get("date")),
                weather=weather,
                high_c=_to_float(cast.get("daytemp")),
                low_c=_to_float(cast.get("nighttemp")),
            )
        )
    return rows


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

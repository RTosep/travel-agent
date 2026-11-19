"""Tests for the travel tools, with HTTP mocked at the transport layer."""

from __future__ import annotations

import json

import httpx

from travel_agent.config import Settings
from travel_agent.tools import build_registry
from travel_agent.tools.currency import convert_currency
from travel_agent.tools.weather import get_weather


def test_weather_uses_amap_geocode_and_amap_weather() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/v3/geocode/geo" in request.url.path:
            assert request.url.params["key"] == "test-amap-key"
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "count": "1",
                    "geocodes": [
                        {
                            "formatted_address": "北京市",
                            "location": "116.407526,39.90403",
                            "city": "北京市",
                            "district": "",
                            "adcode": "110000",
                        }
                    ],
                },
            )

        assert "/v3/weather/weatherInfo" in request.url.path
        assert request.url.params["city"] == "110000"

        if request.url.params.get("extensions") == "base":
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "count": "1",
                    "lives": [
                        {
                            "reporttime": "2026-11-08 12:00:00",
                            "weather": "晴",
                            "temperature": "15",
                            "humidity": "30",
                            "winddirection": "北",
                            "windpower": "3级",
                        }
                    ],
                },
            )

        return httpx.Response(
            200,
            json={
                "status": "1",
                "count": "1",
                "forecasts": [
                    {
                        "casts": [
                            {
                                "date": "2026-11-08",
                                "dayweather": "晴",
                                "nightweather": "多云",
                                "daytemp": "15",
                                "nighttemp": "5",
                            },
                            {
                                "date": "2026-11-09",
                                "dayweather": "小雨",
                                "nightweather": "阴",
                                "daytemp": "13",
                                "nighttemp": "6",
                            },
                        ]
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = get_weather("北京", client=client, amap_key="test-amap-key")

    assert result.location.name == "北京市"
    assert result.location.latitude == 39.90403
    assert result.location.longitude == 116.407526
    assert result.current.weather == "晴"
    assert result.current.temperature_c == 15.0
    assert result.current.humidity == "30"
    assert result.daily[1].weather == "小雨 / 阴"
    assert result.daily[1].high_c == 13.0
    assert result.daily[1].low_c == 6.0
    assert result.weather_source == "高德地图"
    assert result.geocode_source == "高德地图"


def test_weather_rejects_empty_city() -> None:
    assert "error" in get_weather("   ")


def test_currency_converts_with_mocked_rate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["base"] == "CNY"
        assert request.url.params["symbols"] == "JPY"
        return httpx.Response(
            200,
            json={
                "amount": 1000,
                "base": "CNY",
                "date": "2026-11-02",
                "rates": {"JPY": 23.75},
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = convert_currency(1000, "CNY", "JPY", client=client)

    assert result.from_currency == "CNY"
    assert result.to_currency == "JPY"
    assert result.rate == 23.75
    assert result.converted == 23750
    assert result.date == "2026-11-02"


def test_currency_same_code_needs_no_http() -> None:
    result = convert_currency(88, "USD", "USD")

    assert result.rate == 1
    assert result.converted == 88


def test_tool_registry_returns_validation_errors_as_json() -> None:
    registry = build_registry()
    payload = json.loads(
        registry.execute(
            "convert_currency",
            {"amount": 10, "from": "CN", "to": "JPY"},
        )
    )

    assert "error" in payload


def test_tool_registry_rejects_unknown_tool() -> None:
    registry = build_registry()
    payload = json.loads(registry.execute("not_a_tool", {}))

    assert "error" in payload
    assert "未知工具" in payload["error"]


def test_settings_treat_placeholder_key_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-your-key-here")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    assert Settings.from_env().api_key is None


def test_settings_default_to_deepseek_when_key_is_present(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    settings = Settings.from_env()

    assert settings.provider == "deepseek"
    assert settings.provider_label == "DeepSeek"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-flash"


def test_settings_can_force_openai(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    settings = Settings.from_env()

    assert settings.provider == "openai"
    assert settings.provider_label == "OpenAI"
    assert settings.base_url is None
    assert settings.model == "gpt-4o-mini"

"""Tests for the Amap tools, with HTTP mocked at the transport layer."""

from __future__ import annotations

import httpx

from travel_agent.tools.amap import geocode, plan_route, search_poi


def test_amap_geocode_parses_location() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v3/geocode/geo" in request.url.path
        assert request.url.params["key"] == "test-key"
        assert request.url.params["address"] == "北京天安门"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "count": "1",
                "geocodes": [
                    {
                        "formatted_address": "北京市东城区天安门",
                        "location": "116.397428,39.90923",
                        "city": "北京市",
                        "district": "东城区",
                        "adcode": "110101",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = geocode("北京天安门", key="test-key", client=client)

    assert result.longitude == 116.397428
    assert result.latitude == 39.90923
    assert result.name == "北京市东城区天安门"


def test_amap_search_poi_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v3/place/text" in request.url.path
        return httpx.Response(
            200,
            json={
                "status": "1",
                "count": "1",
                "pois": [
                    {
                        "name": "故宫博物院",
                        "address": "北京市东城区景山前街4号",
                        "location": "116.397,39.918",
                        "type": "风景名胜",
                        "tel": "",
                        "biz_ext": {"rating": "5.0", "cost": "60"},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = search_poi("故宫", city="北京", key="test-key", client=client)

    assert result.pois[0].name == "故宫博物院"
    assert result.pois[0].rating == 5.0
    assert result.pois[0].avg_cost == 60.0
    assert result.pois[0].longitude == 116.397
    assert result.pois[0].latitude == 39.918


def test_amap_plan_route_parses_distance_and_duration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/v3/geocode/geo" in request.url.path:
            address = request.url.params["address"]
            assert request.url.params.get("city") == "北京"
            locations = {
                "北京天安门": "116.397428,39.90923",
                "颐和园": "116.2736,39.9999",
            }
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "count": "1",
                    "geocodes": [{"formatted_address": address, "location": locations[address]}],
                },
            )

        assert "/v3/direction/driving" in request.url.path
        return httpx.Response(
            200,
            json={"status": "1", "route": {"paths": [{"distance": "21633", "duration": "2389"}]}},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = plan_route(
            "北京天安门",
            "颐和园",
            mode="driving",
            city="北京",
            key="test-key",
            client=client,
        )

    assert result.distance_km == 21.63
    assert result.duration_min == 39.8
    assert result.origin.name == "北京天安门"
    assert result.destination.name == "颐和园"
    assert result.mode == "driving"


def test_amap_missing_key_returns_error(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_API_KEY", raising=False)

    result = geocode("北京", key=None)

    assert "AMAP_API_KEY" in result["error"]

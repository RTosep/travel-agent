"""Amap (高德地图) tools: geocoding, POI search and route planning.

Amap's Web Service API returns GCJ-02 coordinates (火星坐标), which are
slightly offset from WGS-84. For weather lookup the offset is negligible; for
route planning we keep everything in GCJ-02 consistently.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..models import Location, Poi, PoiSearchResult, Route
from ..trace import get_logger, mask_secret
from .base import Tool

log = get_logger("tools.amap")

AMAP_BASE_URL = "https://restapi.amap.com"
AMAP_PLACEHOLDER = "你的高德Web服务Key"
USER_AGENT = "travel-agent-handrolled/0.1"

DIRECTION_PATHS = {
    "driving": "/v3/direction/driving",
    "walking": "/v3/direction/walking",
    "bicycling": "/v3/direction/bicycling",
    "transit": "/v3/direction/transit/integrated",
}

# 高德个人开发者 Key 通常有 QPS 限制（约 3 次/秒）。
# 全局串行限速，避免并行子 Agent + 连续路径规划把额度打爆。
_AMAP_MIN_INTERVAL = 0.34  # 秒/次，约 2.9 QPS
_AMAP_MAX_ATTEMPTS = 3
_AMAP_RETRY_BASE = 0.8  # 秒，重试退避基数

_RATE_LOCK = threading.Lock()
_LAST_AMAP_REQUEST = 0.0

_GEOCODE_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_GEOCODE_LOCK = threading.Lock()


class AmapError(RuntimeError):
    """Raised when Amap returns a non-success status."""


class SearchPoiArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: str = Field(min_length=1, description="搜索关键词，例如“故宫”“咖啡馆”“酒店”")
    city: str = Field(default="", description="城市名，例如“北京”；留空表示全国搜索")
    offset: int = Field(default=10, ge=1, le=25, description="返回条数，默认 10，最多 25")


class RouteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=1, description="起点，地址或地标名称，例如“北京天安门”")
    destination: str = Field(min_length=1, description="终点，地址或地标名称，例如“颐和园”")
    city: str = Field(default="", description="城市名，用于限定起终点搜索范围，例如“北京”")
    mode: str = Field(
        default="driving",
        description=(
            "出行方式：driving（驾车）/ transit（公交）/ walking（步行）/ bicycling（骑行）"
        ),
    )


def build_amap_poi_tool() -> Tool:
    return Tool(
        name="search_poi",
        description=(
            "用高德地图搜索国内景点、餐厅、酒店、商场等 POI。"
            "返回名称、地址、经纬度、类型、电话、评分、人均消费等。"
        ),
        parameters=SearchPoiArgs.model_json_schema(),
        handler=_handle_search_poi,
    )


def build_amap_route_tool() -> Tool:
    return Tool(
        name="plan_route",
        description=(
            "用高德地图规划国内两点间的驾车/公交/步行/骑行路线。"
            "返回距离（公里）和预计耗时（分钟）。"
            "建议传入 city 以限定城市，避免同名地点定位到别的城市。"
        ),
        parameters=RouteArgs.model_json_schema(),
        handler=_handle_plan_route,
    )


def _handle_search_poi(args: dict[str, Any]) -> PoiSearchResult | dict[str, Any]:
    parsed = SearchPoiArgs.model_validate(args)
    return search_poi(parsed.keywords, city=parsed.city, offset=parsed.offset)


def _handle_plan_route(args: dict[str, Any]) -> Route | dict[str, Any]:
    parsed = RouteArgs.model_validate(args)
    return plan_route(
        parsed.origin,
        parsed.destination,
        mode=parsed.mode,
        city=parsed.city,
    )


def geocode(
    address: str,
    *,
    city: str = "",
    key: str | None = None,
    client: httpx.Client | None = None,
) -> Location | dict[str, Any]:
    log.debug("高德地理编码：address=%r, city=%r", address, city)
    if not address.strip():
        return {"error": "地址不能为空。"}

    cache_key = (address.strip(), city.strip())
    with _GEOCODE_LOCK:
        cached = _GEOCODE_CACHE.get(cache_key)
    if cached is not None:
        log.debug("地理编码命中缓存：%s", cache_key)
        return Location(**cached)

    amap_key, err = resolve_key(key)
    if err:
        return {"error": err}

    params: dict[str, Any] = {"address": address.strip()}
    if city.strip():
        params["city"] = city.strip()

    data, err = amap_call(client, "/v3/geocode/geo", params, amap_key)
    if err:
        return {"error": err}

    geocodes = data.get("geocodes")
    if not isinstance(geocodes, list) or not geocodes:
        return {"error": f"高德没有找到“{address}”的坐标。"}
    item = geocodes[0]
    if not isinstance(item, dict):
        return {"error": "高德地理编码返回了意外的数据格式。"}

    lng, lat = _split_location(item.get("location"))
    if lng is None or lat is None:
        return {"error": f"高德地理编码缺少经纬度：{item.get('location')!r}"}

    log.debug(
        "地理编码结果：%s → lng=%s, lat=%s",
        item.get("formatted_address", address),
        lng,
        lat,
    )
    formatted = clean_str(item.get("formatted_address"))
    location = Location(
        name=formatted or address.strip(),
        address=formatted,
        city=clean_str(item.get("city")),
        district=clean_str(item.get("district")),
        adcode=clean_str(item.get("adcode")),
        longitude=lng,
        latitude=lat,
        source="高德地图",
    )
    with _GEOCODE_LOCK:
        _GEOCODE_CACHE[cache_key] = location.model_dump()
    return location


def search_poi(
    keywords: str,
    *,
    city: str = "",
    offset: int = 10,
    key: str | None = None,
    client: httpx.Client | None = None,
) -> PoiSearchResult | dict[str, Any]:
    log.debug("高德 POI 搜索：keywords=%r, city=%r, offset=%d", keywords, city, offset)
    if not keywords.strip():
        return {"error": "搜索关键词不能为空。"}

    amap_key, err = resolve_key(key)
    if err:
        return {"error": err}

    params: dict[str, Any] = {
        "keywords": keywords.strip(),
        "offset": offset,
        "page": 1,
        "extensions": "all",
    }
    if city.strip():
        params["city"] = city.strip()

    data, err = amap_call(client, "/v3/place/text", params, amap_key)
    if err:
        return {"error": err}

    pois = data.get("pois")
    if not isinstance(pois, list):
        return {"error": "高德 POI 返回了意外的数据格式。"}

    results: list[Poi] = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        lng, lat = _split_location(poi.get("location"))
        biz = poi.get("biz_ext")
        biz = biz if isinstance(biz, dict) else {}
        rating = biz.get("rating")
        cost = biz.get("cost")
        if not isinstance(rating, (str, int, float)):
            rating = None
        if not isinstance(cost, (str, int, float)):
            cost = None
        results.append(
            Poi(
                name=clean_str(poi.get("name")) or "",
                address=clean_str(poi.get("address")),
                longitude=lng,
                latitude=lat,
                source="高德地图",
                category=clean_str(poi.get("type")),
                rating=rating,
                avg_cost=cost,
                telephone=clean_str(poi.get("tel")),
            )
        )

    raw_count = data.get("count")
    try:
        count = int(raw_count)
    except (TypeError, ValueError):
        count = len(results)

    log.debug("POI 搜索返回 %d 条结果", len(results))
    return PoiSearchResult(count=count, pois=results)


def plan_route(
    origin: str,
    destination: str,
    *,
    mode: str = "driving",
    city: str = "",
    key: str | None = None,
    client: httpx.Client | None = None,
) -> Route | dict[str, Any]:
    mode = (mode or "driving").strip().lower()
    log.debug("高德路径规划：%r → %r（mode=%s, city=%r）", origin, destination, mode, city)

    if not origin.strip() or not destination.strip():
        return {"error": "起点和终点不能为空。"}
    if mode not in DIRECTION_PATHS:
        return {"error": f"不支持的出行方式：{mode}，可选 driving/transit/walking/bicycling。"}

    amap_key, err = resolve_key(key)
    if err:
        return {"error": err}

    origin_geo = geocode(origin, city=city, key=amap_key, client=client)
    if isinstance(origin_geo, dict):
        return {"error": f"起点定位失败：{origin_geo['error']}"}

    destination_geo = geocode(destination, city=city, key=amap_key, client=client)
    if isinstance(destination_geo, dict):
        return {"error": f"终点定位失败：{destination_geo['error']}"}

    params = {
        "origin": f"{origin_geo.longitude},{origin_geo.latitude}",
        "destination": f"{destination_geo.longitude},{destination_geo.latitude}",
    }
    data, err = amap_call(client, DIRECTION_PATHS[mode], params, amap_key)
    if err:
        return {"error": err}

    distance_m, duration_s = _extract_route(data, mode)
    log.debug("路径规划结果：distance=%sm, duration=%ss", distance_m, duration_s)

    return Route(
        mode=mode,
        origin=origin_geo,
        destination=destination_geo,
        distance_km=round(distance_m / 1000, 2) if distance_m is not None else None,
        duration_min=round(duration_s / 60, 1) if duration_s is not None else None,
    )


def resolve_key(key: str | None) -> tuple[str, str | None]:
    resolved = (key or "").strip() or _amap_key()
    if not resolved:
        return "", "未配置 AMAP_API_KEY，请在 .env 中填写。"
    return resolved, None


def _amap_key() -> str:
    value = (os.environ.get("AMAP_API_KEY") or "").strip()
    if value == AMAP_PLACEHOLDER:
        return ""
    return value


def amap_call(
    client: httpx.Client | None,
    path: str,
    params: dict[str, Any],
    key: str,
) -> tuple[dict[str, Any], str | None]:
    last_error: str | None = None

    for attempt in range(1, _AMAP_MAX_ATTEMPTS + 1):
        try:
            return _amap_get_json(client, path, params, key), None
        except AmapError as exc:
            last_error = str(exc)
            if not _is_qps_error(last_error):
                return {}, last_error
            if attempt < _AMAP_MAX_ATTEMPTS:
                wait = _AMAP_RETRY_BASE * attempt
                log.warning("高德 QPS 超限，%.1fs 后重试（第 %d 次）", wait, attempt)
                time.sleep(wait)
        except httpx.HTTPStatusError as exc:
            return {}, f"高德接口返回 HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            return {}, f"高德接口请求失败：{exc}"
        except (TypeError, ValueError) as exc:
            return {}, f"高德返回解析失败：{exc}"

    return {}, last_error or "高德接口请求失败"


def _is_qps_error(message: str) -> bool:
    upper = message.upper()
    return "CUQPS" in upper or "QPS" in upper or "LIMIT" in upper


def _throttle() -> None:
    global _LAST_AMAP_REQUEST

    with _RATE_LOCK:
        now = time.monotonic()
        wait = _AMAP_MIN_INTERVAL - (now - _LAST_AMAP_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _LAST_AMAP_REQUEST = time.monotonic()


def _amap_get_json(
    client: httpx.Client | None,
    path: str,
    params: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    _throttle()
    url = f"{AMAP_BASE_URL}{path}"
    merged = {**params, "key": key}
    safe_params = {k: v for k, v in merged.items() if k != "key"}
    log.debug("GET %s params=%s key=%s", url, safe_params, mask_secret(key))

    owns_client = client is None
    http = client or httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT})
    try:
        response = http.get(url, params=merged)
        response.raise_for_status()
        data = response.json()
    finally:
        if owns_client:
            http.close()

    if not isinstance(data, dict):
        raise ValueError("高德返回不是 JSON 对象")

    status = str(data.get("status", ""))
    if status != "1":
        raise AmapError(f"高德接口返回错误（status={status}, info={data.get('info', '未知')}）")

    return data


def _split_location(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, str):
        return None, None
    parts = value.split(",")
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None, None


def clean_str(value: Any) -> str | None:
    """把高德可能返回的空列表/空字符串/None 归一化为字符串或 None。"""

    if isinstance(value, str):
        return value.strip() or None
    return None


def _extract_route(data: dict[str, Any], mode: str) -> tuple[float | None, float | None]:
    route = data.get("route")
    if not isinstance(route, dict):
        return None, None

    if mode in {"driving", "walking", "bicycling"}:
        paths = route.get("paths")
        if isinstance(paths, list) and paths and isinstance(paths[0], dict):
            first = paths[0]
            return _to_number(first.get("distance")), _to_number(first.get("duration"))

    transits = route.get("transits")
    if isinstance(transits, list) and transits and isinstance(transits[0], dict):
        first = transits[0]
        distance = _to_number(first.get("distance"))
        if distance is None:
            distance = _to_number(route.get("distance"))
        duration = _to_number(first.get("duration"))
        if duration is None:
            duration = _to_number(route.get("duration"))
        return distance, duration

    return _to_number(route.get("distance")), _to_number(route.get("duration"))


def _to_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

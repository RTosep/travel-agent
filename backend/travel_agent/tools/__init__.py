"""Travel tools and their registry."""

from __future__ import annotations

from .amap import build_amap_poi_tool, build_amap_route_tool
from .base import Tool, ToolRegistry
from .currency import build_currency_tool
from .weather import build_weather_tool


def build_travel_tools() -> list[Tool]:
    return [
        build_weather_tool(),
        build_currency_tool(),
        build_amap_poi_tool(),
        build_amap_route_tool(),
    ]


def build_registry() -> ToolRegistry:
    return ToolRegistry(build_travel_tools())


__all__ = [
    "Tool",
    "ToolRegistry",
    "build_registry",
    "build_travel_tools",
]

"""MCP server：把旅行工具通过 stdio 暴露出去。

运行方式：
    python -m travel_agent.mcp.server

客户端（MCPClient）会以子进程方式启动它，然后通过 JSON-RPC（stdio）交互。
"""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from ..tools.amap import plan_route as _plan_route
from ..tools.amap import search_poi as _search_poi
from ..tools.base import model_to_json
from ..tools.currency import convert_currency as _convert_currency
from ..tools.weather import get_weather as _get_weather

logging.getLogger("httpx").setLevel(logging.WARNING)

# server 是独立子进程，也要自己加载 backend/.env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

mcp = MCPServer(
    "travel-agent-amap",
    instructions="高德地图与旅行辅助工具：POI 搜索、路径规划、天气、汇率。",
)


@mcp.tool(name="search_poi")
def search_poi(keywords: str, city: str = "", offset: int = 10) -> str:
    """用高德地图搜索 POI（景点/餐厅/酒店/商场等），返回结构化 JSON。"""
    return model_to_json(_search_poi(keywords, city=city, offset=offset))


@mcp.tool(name="plan_route")
def plan_route(origin: str, destination: str, mode: str = "driving", city: str = "") -> str:
    """用高德地图规划两点间的交通，返回距离和耗时。"""
    return model_to_json(_plan_route(origin, destination, mode=mode, city=city))


@mcp.tool(name="get_weather")
def get_weather(city: str) -> str:
    """查询城市当前天气和未来 4 天预报。"""
    return model_to_json(_get_weather(city))


@mcp.tool(name="convert_currency")
def convert_currency(
    amount: float,
    from_currency: str = "CNY",
    to_currency: str = "CNY",
) -> str:
    """按最新参考汇率换算货币。"""
    return model_to_json(_convert_currency(amount, from_currency, to_currency))


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()

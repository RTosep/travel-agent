"""HotelAgent：酒店查询子 Agent。"""

from __future__ import annotations

from ..models import HotelSearchResult
from ..tools.amap import build_amap_poi_tool
from ..tools.base import Tool, ToolRegistry
from .base import Agent

INSTRUCTIONS = """你是一个酒店查询专员，只负责找酒店，不负责别的。

用户会给一个 JSON，例如 {"city": "深圳", "keywords": "舒适 近地铁 预算500"}：
- city：城市名
- keywords：住宿偏好

1. 调用 search_poi 搜索酒店（city 传城市，keywords 传“酒店”和用户偏好，offset 传 10）。
2. 从返回的 pois 里筛选出「住宿」类，去掉停车场、公交站等无关 POI。
3. 整理成 JSON 对象，结构见【输出要求】。
   注意：POI 的 avg_cost 对应 price_per_night（每晚价格）；
   category 里若含“五星级/三星级/经济型”等，可解析出 star（星级，纯数字）。
"""


class HotelAgent(Agent):
    def __init__(
        self,
        *,
        client,
        model: str,
        max_turns: int = 6,
        tools: list[Tool] | None = None,
    ) -> None:
        registry = ToolRegistry(tools or [build_amap_poi_tool()])
        super().__init__(
            name="HotelAgent",
            instructions=INSTRUCTIONS,
            registry=registry,
            model=model,
            client=client,
            max_turns=max_turns,
            output_model=HotelSearchResult,
        )

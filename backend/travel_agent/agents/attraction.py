"""AttractionSearchAgent：景点搜索子 Agent。"""

from __future__ import annotations

from ..models import AttractionSearchResult
from ..tools.amap import build_amap_poi_tool
from ..tools.base import Tool, ToolRegistry
from .base import Agent

INSTRUCTIONS = """你是一个景点搜索专员，只负责找景点，不负责别的。

用户会给一个 JSON，例如 {"city": "深圳", "keywords": "海滨 公园 博物馆"}：
- city：城市名
- keywords：兴趣关键词

1. 调用 search_poi 搜索（city 传城市，keywords 传兴趣词，offset 传 10）。
2. 从返回的 pois 里，筛选出真正值得游玩的「景点」类（风景名胜、公园、博物馆、寺庙等），
   去掉地铁站、停车场、售票处、卫生间等无关 POI。
3. 把筛选结果整理成 JSON 对象，结构见【输出要求】。
   注意：POI 的 avg_cost 字段对应景点的 ticket_price（门票）；category 对应景点类型。
"""


class AttractionSearchAgent(Agent):
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
            name="AttractionSearchAgent",
            instructions=INSTRUCTIONS,
            registry=registry,
            model=model,
            client=client,
            max_turns=max_turns,
            output_model=AttractionSearchResult,
        )

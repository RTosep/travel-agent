"""WeatherQueryAgent：天气查询子 Agent。"""

from __future__ import annotations

from ..models import WeatherReport
from ..tools.base import Tool, ToolRegistry
from ..tools.weather import build_weather_tool
from .base import Agent

INSTRUCTIONS = """你是一个天气查询专员，只负责查天气，不负责别的。

用户会给一个 JSON，例如 {"city": "深圳"}，city 是要查询的城市。

1. 调用 get_weather 工具查询该城市的天气。
2. get_weather 的返回结果已经是结构化 JSON，把它作为你的最终输出原样输出，
   不要改字段名，不要加解释文字。
"""


class WeatherQueryAgent(Agent):
    def __init__(
        self,
        *,
        client,
        model: str,
        max_turns: int = 6,
        tools: list[Tool] | None = None,
    ) -> None:
        registry = ToolRegistry(tools or [build_weather_tool()])
        super().__init__(
            name="WeatherQueryAgent",
            instructions=INSTRUCTIONS,
            registry=registry,
            model=model,
            client=client,
            max_turns=max_turns,
            output_model=WeatherReport,
        )

"""Minimal tool abstraction used by the hand-rolled agent loop."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ..trace import get_logger

log = get_logger("tools.registry")

ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class Tool:
    """A function exposed to the model through the Chat Completions tools API."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Looks up tools by name and turns every failure into model-visible JSON."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"重复的工具名称：{tool.name}")
            self._tools[tool.name] = tool

        log.debug("工具注册表构建完成，共 %d 个工具：%s", len(self._tools), ", ".join(self._tools))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        specs = [tool.spec() for tool in self._tools.values()]
        log.debug(
            "生成工具定义（发给模型的 tools 参数）：\n%s",
            json.dumps(specs, ensure_ascii=False, indent=2),
        )
        return specs

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            log.warning("未知工具：%s", name)
            return _error_json(f"未知工具：{name}")

        log.debug("── 执行工具 %s ──", name)
        log.debug("入参：%s", json.dumps(arguments, ensure_ascii=False))

        try:
            result = tool.handler(arguments)
            result_json = model_to_json(result)
        except Exception as exc:  # noqa: BLE001 - tool errors must be model-visible
            log.warning("工具 %s 执行异常：%s", name, exc)
            return _error_json(f"工具 {name} 执行失败：{exc}")

        class_name = type(result).__name__ if isinstance(result, BaseModel) else "error"
        if isinstance(result, BaseModel) and hasattr(result, "summarize"):
            log.info("工具 %s [%s] → %s", name, class_name, result.summarize())
        else:
            log.info("工具 %s [%s] → %s", name, class_name, result_json)
        log.debug("工具 %s 完整结果：%s", name, result_json)
        return result_json


def model_to_json(value: Any) -> str:
    """把工具返回值序列化为 JSON 字符串。

    支持 Pydantic 模型、模型列表、普通 dict 等。模型序列化时使用别名并省略 None。
    """

    if isinstance(value, BaseModel):
        return value.model_dump_json(by_alias=True, exclude_none=True)

    if isinstance(value, (list, tuple)):
        items = [
            item.model_dump(by_alias=True, exclude_none=True)
            if isinstance(item, BaseModel)
            else item
            for item in value
        ]
        return json.dumps(items, ensure_ascii=False)

    return json.dumps(value, ensure_ascii=False, default=str)


def _error_json(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)

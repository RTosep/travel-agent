"""Agent 基类：手写的工具调用循环，被各子 Agent 复用。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from json_repair import repair_json
from openai import OpenAI
from pydantic import BaseModel

from ..runs import RunRecorder
from ..tools.base import ToolRegistry
from ..trace import get_logger, truncate

log = get_logger("agent")

EventSink = Callable[[dict[str, Any]], None]


def _noop_sink(_: dict[str, Any]) -> None:
    pass


class AgentError(RuntimeError):
    """Agent 基类错误。"""


class AgentLoopError(AgentError):
    """超过最大轮数仍未产出最终回答。"""


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass(frozen=True, slots=True)
class AgentReply:
    text: str
    tool_calls: tuple[ToolCallRecord, ...] = ()


class Agent:
    """一个带工具调用能力的最小 Agent。

    通过 `output_model` 可以要求 Agent 输出结构化 JSON 并校验。
    """

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        registry: ToolRegistry,
        model: str,
        client: OpenAI,
        max_turns: int = 8,
        output_model: type[BaseModel] | None = None,
        event_sink: EventSink | None = None,
        recorder: RunRecorder | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns 必须大于 0")

        self.name = name
        self.instructions = instructions
        self.model = model
        self._client = client
        self._max_turns = max_turns
        self._output_model = output_model
        self._registry = registry
        self._event_sink: EventSink = event_sink or _noop_sink
        self._recorder = recorder
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._instructions_with_schema()}
        ]

        log.debug(
            "[%s] 初始化：model=%s, max_turns=%d, tools=%s",
            name,
            model,
            max_turns,
            ", ".join(registry.names),
        )

    def _instructions_with_schema(self) -> str:
        text = self.instructions
        if self._output_model is not None:
            schema = json.dumps(self._output_model.model_json_schema(), ensure_ascii=False)
            text += (
                "\n\n【输出要求】最终回答必须是一个 JSON 对象，严格符合下面的 JSON Schema，"
                "只输出 JSON 本身，不要输出任何解释文字或 Markdown 代码块：\n" + schema
            )
        return text

    @property
    def messages(self) -> list[dict[str, Any]]:
        return [dict(message) for message in self._messages]

    @property
    def tool_names(self) -> tuple[str, ...]:
        return self._registry.names

    def set_event_sink(self, sink: EventSink | None) -> None:
        self._event_sink = sink or _noop_sink

    def set_recorder(self, recorder: RunRecorder | None) -> None:
        self._recorder = recorder

    def _emit(self, event_type: str, message: str, **data: Any) -> None:
        try:
            self._event_sink(
                {
                    "type": event_type,
                    "agent": self.name,
                    "message": message,
                    "data": data or None,
                }
            )
        except Exception:  # noqa: BLE001 - 事件回调不能影响主流程
            log.debug("[%s] 事件回调失败", self.name, exc_info=True)

    def run(self, user_input: str) -> AgentReply:
        prompt = user_input.strip()
        if not prompt:
            raise ValueError("输入不能为空")

        log.info("[%s] 开始处理", self.name)
        self._emit("agent_start", f"{self.name} 开始处理")
        log.debug("[%s] 收到输入：%s", self.name, truncate(prompt, 120))
        self._messages.append({"role": "user", "content": prompt})
        tool_records: list[ToolCallRecord] = []

        for turn in range(1, self._max_turns + 1):
            log.debug("[%s] 第 %d/%d 轮", self.name, turn, self._max_turns)
            specs = self._registry.specs()

            if self._recorder is not None:
                self._recorder.llm(
                    {
                        "type": "request",
                        "agent": self.name,
                        "model": self.model,
                        "messages": self.messages,
                        "tools": specs,
                    }
                )

            try:
                request: dict[str, Any] = {
                    "model": self.model,
                    "messages": self._messages,
                    "max_tokens": 8192,
                    "extra_body": {"thinking": {"type": "enabled"}},
                }
                if specs:
                    request["tools"] = specs
                    request["tool_choice"] = "auto"

                response = self._client.chat.completions.create(**request)
            except Exception as exc:
                if self._recorder is not None:
                    self._recorder.llm({"type": "error", "agent": self.name, "error": str(exc)})
                raise

            if not response.choices:
                raise AgentError("模型没有返回任何候选结果。")

            message = response.choices[0].message

            if self._recorder is not None:
                usage = getattr(response, "usage", None)
                self._recorder.llm(
                    {
                        "type": "response",
                        "agent": self.name,
                        "finish_reason": getattr(response.choices[0], "finish_reason", None),
                        "message": message.model_dump(exclude_none=True),
                        "usage": usage.model_dump() if usage is not None else None,
                    }
                )

            self._messages.append(message.model_dump(exclude_none=True))

            tool_calls = message.tool_calls or []
            if not tool_calls:
                text = (message.content or "").strip()
                if not text:
                    raise AgentError("模型返回了空内容。")
                return AgentReply(text=text, tool_calls=tuple(tool_records))

            for call in tool_calls:
                arguments, parse_error = _parse_arguments(call.function.arguments)
                self._emit(
                    "tool_call",
                    f"调用 {call.function.name}",
                    tool=call.function.name,
                    arguments=arguments,
                )
                if parse_error is not None:
                    result = json.dumps({"error": parse_error}, ensure_ascii=False)
                else:
                    result = self._registry.execute(call.function.name, arguments)

                if self._recorder is not None:
                    self._recorder.tool(
                        {
                            "agent": self.name,
                            "name": call.function.name,
                            "arguments": arguments,
                            "parse_error": parse_error,
                            "result": result,
                        }
                    )

                self._emit("tool_result", f"{call.function.name} 完成", tool=call.function.name)
                tool_records.append(
                    ToolCallRecord(name=call.function.name, arguments=arguments, result=result)
                )
                self._messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        raise AgentLoopError(f"超过最大轮数 {self._max_turns}，Agent 仍未给出最终回答。")

    def run_structured(self, user_input: str) -> BaseModel:
        if self._output_model is None:
            raise AgentError(f"Agent {self.name} 没有定义输出模型")

        prompt = user_input
        last_error: Exception | None = None

        for attempt in range(1, 3):
            reply = self.run(prompt)
            text = _extract_json(reply.text)

            try:
                data = _parse_json_object(text)
                result = self._output_model.model_validate(data)
            except Exception as exc:
                last_error = exc
                if attempt == 1:
                    log.warning("[%s] 结构化输出校验失败，准备重试：%s", self.name, exc)
                    self._emit(
                        "agent_retry",
                        f"{self.name} 输出不合法，正在自动修复",
                        error=truncate(str(exc), 300),
                    )
                    prompt = (
                        "你上一次的输出不是合法 JSON，或字段不符合要求。"
                        "请修正后重新输出，只输出 JSON，不要解释。\n"
                        f"错误：{exc}\n"
                        f"上一次输出：{truncate(reply.text, 2000)}"
                    )
                    continue

                raise AgentError(
                    f"Agent {self.name} 的输出无法解析为 {self._output_model.__name__}：{exc}\n"
                    f"原始输出：{truncate(reply.text, 400)}"
                ) from exc

            summary = result.summarize() if hasattr(result, "summarize") else type(result).__name__
            log.info("[%s] 输出：%s", self.name, summary)
            self._emit("agent_result", f"{self.name}：{summary}", summary=summary)
            return result

        raise AgentError(
            f"Agent {self.name} 的输出无法解析为 {self._output_model.__name__}：{last_error}"
        )


def _parse_arguments(raw: str | None) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {}, f"工具参数不是合法 JSON：{exc.msg}"

    if not isinstance(value, dict):
        return {}, "工具参数必须是 JSON 对象。"

    return value, None


def _parse_json_object(text: str) -> dict[str, Any]:
    """先严格解析，失败后用 json_repair 容错修复（少逗号、尾逗号等）。"""

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = repair_json(text, return_objects=True)

    if not isinstance(value, dict):
        raise ValueError("模型输出不是 JSON 对象")

    return value


def _extract_json(text: str) -> str:
    text = (text or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


# 兼容旧名字，便于平滑迁移
TravelAgent = Agent

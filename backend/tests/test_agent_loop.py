"""Tests for the hand-rolled loop, using a fake OpenAI client."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from travel_agent.agents.base import Agent, AgentLoopError, _extract_json
from travel_agent.tools.base import Tool, ToolRegistry


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction
    type: str = "function"

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[FakeToolCall] | None = None
    reasoning_content: str | None = None

    def model_dump(self, **_: Any) -> dict[str, Any]:
        data: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [call.model_dump() for call in self.tool_calls]
        if self.reasoning_content is not None:
            data["reasoning_content"] = self.reasoning_content
        return data


class FakeCompletions:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = list(messages)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._messages:
            raise AssertionError("fake client ran out of responses")
        message = self._messages.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(messages))


class FakeOutput(BaseModel):
    city: str
    days: int


def test_agent_executes_tool_then_returns_final_text() -> None:
    tool_calls = [
        FakeToolCall(
            id="call_1",
            function=FakeFunction("get_weather", '{"city": "京都"}'),
        )
    ]
    client = FakeClient(
        [
            FakeMessage(content=None, tool_calls=tool_calls),
            FakeMessage(content="京都今天多云，建议带一把折叠伞。"),
        ]
    )

    seen: list[dict[str, Any]] = []

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        seen.append(arguments)
        return {"weather": "多云", "temperature_c": 19}

    tool = Tool(
        name="get_weather",
        description="test weather tool",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        handler=handler,
    )

    agent = Agent(
        name="test",
        instructions="test system prompt",
        client=cast(Any, client),
        registry=ToolRegistry([tool]),
        model="test-model",
        max_turns=4,
    )

    reply = agent.run("京都今天天气怎么样？")

    assert reply.text == "京都今天多云，建议带一把折叠伞。"
    assert seen == [{"city": "京都"}]
    assert len(reply.tool_calls) == 1
    assert reply.tool_calls[0].name == "get_weather"
    assert reply.tool_calls[0].arguments == {"city": "京都"}
    assert '"weather": "多云"' in reply.tool_calls[0].result

    messages = agent.messages
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert messages[3]["tool_call_id"] == "call_1"

    completions = client.chat.completions
    assert completions.calls[0]["tools"][0]["function"]["name"] == "get_weather"
    assert completions.calls[0]["tool_choice"] == "auto"


def test_agent_turns_malformed_arguments_into_tool_error() -> None:
    tool_calls = [
        FakeToolCall(
            id="call_bad",
            function=FakeFunction("get_weather", "{not-json"),
        )
    ]
    client = FakeClient(
        [
            FakeMessage(content=None, tool_calls=tool_calls),
            FakeMessage(content="工具参数有问题，我无法查询。"),
        ]
    )

    agent = Agent(
        name="test",
        instructions="test",
        client=cast(Any, client),
        registry=ToolRegistry([]),
        model="test-model",
        max_turns=2,
    )

    reply = agent.run("查天气")

    assert reply.tool_calls[0].arguments == {}
    assert "JSON" in reply.tool_calls[0].result
    assert reply.text == "工具参数有问题，我无法查询。"


def test_agent_stops_after_max_turns() -> None:
    call = FakeToolCall(
        id="call_loop",
        function=FakeFunction("get_weather", '{"city": "京都"}'),
    )
    client = FakeClient(
        [
            FakeMessage(content=None, tool_calls=[call]),
            FakeMessage(content=None, tool_calls=[call]),
        ]
    )

    agent = Agent(
        name="test",
        instructions="test",
        client=cast(Any, client),
        registry=ToolRegistry(
            [
                Tool(
                    name="get_weather",
                    description="test",
                    parameters={"type": "object"},
                    handler=lambda _: {"ok": True},
                )
            ]
        ),
        model="test-model",
        max_turns=2,
    )

    with pytest.raises(AgentLoopError, match="最大轮数"):
        agent.run("一直查天气")


def test_agent_preserves_deepseek_reasoning_content() -> None:
    call = FakeToolCall(
        id="call_currency",
        function=FakeFunction(
            "convert_currency",
            '{"amount": 100, "from": "CNY", "to": "CNY"}',
        ),
    )
    client = FakeClient(
        [
            FakeMessage(
                content=None,
                tool_calls=[call],
                reasoning_content="先调用汇率工具。",
            ),
            FakeMessage(
                content="100 CNY 就是 100 CNY。",
                reasoning_content="工具已经返回结果，可以回答。",
            ),
        ]
    )

    agent = Agent(
        name="test",
        instructions="test",
        client=cast(Any, client),
        registry=ToolRegistry(
            [
                Tool(
                    name="convert_currency",
                    description="test",
                    parameters={"type": "object"},
                    handler=lambda _: {"converted": 100},
                )
            ]
        ),
        model="deepseek-flash",
        max_turns=2,
    )

    reply = agent.run("100 CNY 换 CNY 是多少？")

    assert reply.text == "100 CNY 就是 100 CNY。"
    assert agent.messages[2]["reasoning_content"] == "先调用汇率工具。"
    assert agent.messages[4]["reasoning_content"] == "工具已经返回结果，可以回答。"

    second_request_messages = client.chat.completions.calls[1]["messages"]
    assert second_request_messages[2]["reasoning_content"] == "先调用汇率工具。"


def test_agent_run_structured_validates_json() -> None:
    client = FakeClient([FakeMessage(content='{"city": "深圳", "days": 3}')])

    agent = Agent(
        name="test",
        instructions="只输出 JSON",
        client=cast(Any, client),
        registry=ToolRegistry([]),
        model="test-model",
        max_turns=2,
        output_model=FakeOutput,
    )

    result = agent.run_structured("深圳三日")

    assert isinstance(result, FakeOutput)
    assert result.city == "深圳"
    assert result.days == 3
    assert client.chat.completions.calls[0]["max_tokens"] == 8192


def test_agent_run_structured_repairs_trailing_comma() -> None:
    client = FakeClient([FakeMessage(content='{"city": "深圳", "days": 3,}')])

    agent = Agent(
        name="test",
        instructions="只输出 JSON",
        client=cast(Any, client),
        registry=ToolRegistry([]),
        model="test-model",
        max_turns=2,
        output_model=FakeOutput,
    )

    result = agent.run_structured("深圳三日")

    assert result.city == "深圳"
    assert result.days == 3


def test_agent_run_structured_retries_after_invalid_json() -> None:
    client = FakeClient(
        [
            FakeMessage(content='{"city": "深圳", "days": "three"}'),
            FakeMessage(content='{"city": "深圳", "days": 3}'),
        ]
    )
    events: list[dict[str, Any]] = []

    agent = Agent(
        name="test",
        instructions="只输出 JSON",
        client=cast(Any, client),
        registry=ToolRegistry([]),
        model="test-model",
        max_turns=2,
        output_model=FakeOutput,
        event_sink=events.append,
    )

    result = agent.run_structured("深圳三日")

    assert result.days == 3
    assert len(client.chat.completions.calls) == 2
    assert any(event["type"] == "agent_retry" for event in events)


def test_extract_json_handles_code_fence() -> None:
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('前缀 {"a": 1} 后缀') == '{"a": 1}'


def test_openai_sdk_keeps_deepseek_reasoning_content() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "先查汇率。",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "convert_currency",
                                    "arguments": '{"amount": 1, "from": "CNY", "to": "CNY"}',
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )

    dumped = completion.choices[0].message.model_dump(exclude_none=True)

    assert dumped["reasoning_content"] == "先查汇率。"

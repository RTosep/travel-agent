"""MCP client：通过 stdio 连接 MCP server，并把工具适配成 Agent 用的 Tool。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp import types as mcp_types
from mcp.client.stdio import stdio_client

from ..tools.base import Tool
from ..trace import get_logger

log = get_logger("mcp.client")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class MCPClient:
    """在后台线程跑 asyncio 事件循环，对外提供同步的 call_tool。"""

    def __init__(self, command: str | None = None, args: list[str] | None = None) -> None:
        self._command = command or sys.executable
        self._args = args or ["-m", "travel_agent.mcp.server"]
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._session: ClientSession | None = None
        self._tools: list[mcp_types.Tool] = []
        self._ready = threading.Event()
        self._stop = asyncio.Event()
        self._error: BaseException | None = None

    @property
    def tools(self) -> list[mcp_types.Tool]:
        return list(self._tools)

    def start(self, timeout: float = 20.0) -> MCPClient:
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("MCP server 启动超时")
        if self._error is not None:
            raise RuntimeError(f"MCP server 启动失败：{self._error}") from self._error
        log.info("MCP 已连接，工具：%s", ", ".join(tool.name for tool in self._tools))
        return self

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: float = 60.0) -> Any:
        if self._session is None:
            raise RuntimeError("MCP client 尚未连接")

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop,
        )
        result = future.result(timeout=timeout)
        return _parse_result(result)

    def stop(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=10)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - 记录启动/运行错误
            self._error = exc
            self._ready.set()
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        params = StdioServerParameters(
            command=self._command,
            args=self._args,
            cwd=str(PROJECT_ROOT),
            env=dict(os.environ),
        )
        try:
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                listed = await session.list_tools()
                self._tools = listed.tools
                self._session = session
                self._ready.set()
                await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - 通过 _error 抛给调用方
            self._error = exc
            self._ready.set()
        finally:
            self._session = None


def _parse_result(result: mcp_types.CallToolResult) -> Any:
    text = _content_text(result)
    if result.is_error:
        raise RuntimeError(text or "MCP 工具执行失败")

    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP 返回的不是 JSON：{exc}\n原始内容：{text[:400]}") from exc


def _content_text(result: mcp_types.CallToolResult) -> str:
    parts: list[str] = []
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def mcp_tool(client: MCPClient, tool: mcp_types.Tool) -> Tool:
    """把 MCP 工具定义包装成项目里的 Tool。"""

    def handler(arguments: dict[str, Any]) -> Any:
        return client.call_tool(tool.name, arguments)

    return Tool(
        name=tool.name,
        description=tool.description or tool.name,
        parameters=tool.input_schema,
        handler=handler,
    )

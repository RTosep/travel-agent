"""Tests for the MCP tool adapter (no subprocess needed)."""

from __future__ import annotations

from types import SimpleNamespace

from travel_agent.mcp.client import mcp_tool


def test_mcp_tool_forwards_to_client() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name: str, arguments: dict):
            self.calls.append((name, arguments))
            return {"ok": True, "name": name}

    client = FakeClient()
    definition = SimpleNamespace(
        name="search_poi",
        description="搜索 POI",
        input_schema={"type": "object", "properties": {"keywords": {"type": "string"}}},
    )

    tool = mcp_tool(client, definition)

    assert tool.name == "search_poi"
    assert tool.description == "搜索 POI"
    assert tool.parameters == definition.input_schema
    assert tool.handler({"keywords": "公园"}) == {"ok": True, "name": "search_poi"}
    assert client.calls == [("search_poi", {"keywords": "公园"})]

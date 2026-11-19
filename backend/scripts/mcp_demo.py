"""MCP 交互演示：连接 server，列出工具，调用一个工具。

运行：
    make mcp-demo
    # 或 .venv/bin/python scripts/mcp_demo.py

这个 demo 只调用 convert_currency（汇率），不会消耗高德额度。
"""

from __future__ import annotations

import json

from travel_agent.mcp.client import MCPClient


def main() -> None:
    client = MCPClient().start()
    try:
        print("已连接 MCP server")
        print("可用工具：")
        for tool in client.tools:
            print(f"- {tool.name}: {tool.description}")

        print("\n调用 convert_currency(amount=1000, from=CNY, to=JPY)：")
        result = client.call_tool(
            "convert_currency",
            {"amount": 1000, "from_currency": "CNY", "to_currency": "JPY"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        client.stop()


if __name__ == "__main__":
    main()

"""End-to-end check of the Plan-and-Resolve + Reflection pipeline.

No API key and no external API calls. The mock inspects the system prompt to
decide which agent is calling, and returns a canned structured JSON for each:

- PlanAgent              -> ResearchPlan
- AttractionSearchAgent  -> {"attractions": []}
- WeatherQueryAgent      -> {"location": {"name": "深圳市"}, "daily": []}
- HotelAgent             -> {"hotels": []}
- DraftPlannerAgent      -> a minimal TripPlan (draft + revise)
- ReflectionAgent        -> ReflectionReport with should_revise=true

This verifies: plan -> resolve -> draft -> reflect -> revise, per-agent result
logging, structured output validation, and the final TripPlan print.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TITLE = "端到端测试"

RESPONSES = {
    "旅行研究规划师": {
        "destination": "深圳",
        "dates": "3 天",
        "travelers": "双人",
        "constraints": ["非自驾"],
        "tasks": [
            {"kind": "attraction", "query": "深圳湾公园", "reason": "看海", "priority": 1},
            {"kind": "weather", "query": "深圳天气", "reason": "安排室内外", "priority": 2},
            {"kind": "hotel", "query": "近地铁酒店", "reason": "住宿", "priority": 2},
        ],
        "reflection_focus": ["节奏", "交通"],
        "summary": "先查景点天气酒店，再排行程",
    },
    "景点搜索专员": {"attractions": []},
    "天气查询专员": {"location": {"name": "深圳市"}, "daily": []},
    "酒店查询专员": {"hotels": []},
    "旅行总规划师": {"title": EXPECTED_TITLE, "destination": "深圳", "days": []},
    "严格的旅行行程审阅者": {
        "score": 7,
        "should_revise": True,
        "issues": [
            {
                "category": "pace",
                "severity": "medium",
                "description": "第一天安排偏多",
                "suggestion": "减少一个景点",
            }
        ],
        "summary": "节奏略紧，建议精简",
    },
}


class MockOpenAIHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        self.requests.append(body)

        system = body["messages"][0]["content"]
        content = "{}"
        for marker, payload in RESPONSES.items():
            if marker in system:
                content = json.dumps(payload, ensure_ascii=False)
                break

        message = {"role": "assistant", "content": content}
        response = {
            "id": "chatcmpl-local-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    MockOpenAIHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    env = {
        **os.environ,
        "LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "test-key",
        "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{port}",
        "DEEPSEEK_MODEL": "test-model",
        "TRAVEL_AGENT_RUNS_DIR": tempfile.mkdtemp(prefix="travel-agent-e2e-"),
        # Bypass a system-wide proxy for the local mock server.
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }

    try:
        command = [sys.executable, "-m", "travel_agent"]
        if "--mcp" in sys.argv[1:]:
            command.append("--mcp")
        command.append("深圳三日游")
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=90,
        )
    finally:
        server.shutdown()

    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    assert result.returncode == 0, f"CLI exited with {result.returncode}"
    assert f"# {EXPECTED_TITLE}" in result.stdout, "TripPlan markdown title was not printed"
    assert "目的地：深圳" in result.stdout, "TripPlan markdown body was not printed"

    if "--mcp" in sys.argv[1:]:
        assert "MCP 已连接" in result.stderr, "MCP client did not connect"

    # PlanAgent(1) + 3 个子 Agent(3) + Draft(2) + Reflection(2) = 8
    assert len(MockOpenAIHandler.requests) == 8, (
        f"expected 8 model calls, got {len(MockOpenAIHandler.requests)}"
    )

    # 每个阶段都打印了自己的结果
    for agent_name in (
        "PlanAgent",
        "AttractionSearchAgent",
        "WeatherQueryAgent",
        "HotelAgent",
        "DraftPlannerAgent",
        "ReflectionAgent",
    ):
        assert f"[{agent_name}]" in result.stderr, f"{agent_name} result was not logged"

    plan_requests = [
        request
        for request in MockOpenAIHandler.requests
        if "旅行研究规划师" in request["messages"][0]["content"]
    ]
    assert len(plan_requests) == 1, "expected exactly one PlanAgent call"

    draft_requests = [
        request
        for request in MockOpenAIHandler.requests
        if "旅行总规划师" in request["messages"][0]["content"]
    ]
    assert len(draft_requests) == 2, "expected one draft + one revise call"
    draft_user_message = draft_requests[0]["messages"][1]["content"]
    assert "研究计划" in draft_user_message
    assert "以下是按计划检索到的资料" in draft_user_message
    revise_user_message = draft_requests[1]["messages"][-1]["content"]
    assert "审阅意见" in revise_user_message

    reflect_requests = [
        request
        for request in MockOpenAIHandler.requests
        if "严格的旅行行程审阅者" in request["messages"][0]["content"]
    ]
    assert len(reflect_requests) == 2, "expected two reflection rounds"
    assert "行程草稿" in reflect_requests[0]["messages"][1]["content"]

    print(
        "\nE2E OK: Plan -> Resolve -> Draft -> Reflect -> Revise, "
        "each phase logged its result, and the final TripPlan printed."
    )


if __name__ == "__main__":
    main()

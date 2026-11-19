"""Command-line interface for the travel agent."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from typing import Any

from openai import OpenAI
from prompt_toolkit import PromptSession

from .agents.planner import PlannerAgent, build_planner
from .config import Settings
from .mcp.client import MCPClient, mcp_tool
from .runs import RunRecorder
from .trace import configure, get_logger, mask_secret, truncate

log = get_logger("cli")

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="travel-agent",
        description="多 Agent 手搓旅行规划（PlannerAgent 编排子 Agent）",
    )
    parser.add_argument("prompt", nargs="*", help="一次性旅行需求；省略则进入交互模式")
    parser.add_argument(
        "-v",
        "--verbose",
        "--trace",
        action="store_true",
        dest="trace",
        help="打印完整 trace（DEBUG 级别：URL、参数、原始 JSON）",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="关闭 trace，只输出最终回答和错误",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出原始 TripPlan JSON（默认输出可读的 Markdown 攻略）",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="通过 MCP server 调用高德/汇率工具（默认进程内直连）",
    )
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.trace else logging.WARNING if args.quiet else logging.INFO
    configure(level)
    log.debug("========== 启动 ==========")
    log.debug("trace 级别：%s", logging.getLevelName(level))
    log.debug("命令行 prompt：%s", truncate(" ".join(args.prompt), 120) or "<空，进入交互模式>")

    settings = Settings.from_env()
    if settings.api_key is None:
        log.warning("api_key 无效，无法启动")
        print(
            "缺少 API Key。\n\n"
            "DeepSeek：在 .env 中填 DEEPSEEK_API_KEY\n"
            "OpenAI：  在 .env 中填 OPENAI_API_KEY\n\n"
            "如果还没有 .env：\n"
            "  cp .env.example .env\n",
            file=sys.stderr,
        )
        return 1

    mcp_client: MCPClient | None = None
    try:
        tool_overrides: dict[str, Any] | None = None
        if args.mcp:
            mcp_client = MCPClient().start()
            tool_overrides = {tool.name: mcp_tool(mcp_client, tool) for tool in mcp_client.tools}
            print(f"MCP 已连接，工具：{', '.join(tool_overrides)}", file=sys.stderr)

        agent = _build_agent(settings, tool_overrides)
        log.debug("Agent 构建完成：provider=%s, model=%s", settings.provider_label, settings.model)

        prompt = " ".join(args.prompt).strip()

        if prompt:
            log.debug("单次模式")
            recorder = RunRecorder(prompt, metadata={"source": "cli"})
            agent.set_recorder(recorder)
            log.info("运行记录：%s", recorder.dir)

            try:
                result = agent.plan(prompt)
                recorder.finish(status="ok", result=result.model_dump(mode="json"))
                _print_trip(result, as_json=args.json)
            except Exception as exc:  # noqa: BLE001 - CLI must show the failure
                recorder.finish(status="error", error=traceback.format_exc())
                log.error("单次请求失败：%s", exc)
                print(f"请求失败：{exc}", file=sys.stderr)
                return 1
            finally:
                agent.set_recorder(None)
            return 0

        log.debug("进入交互模式")
        print(
            "\nTravel Agent（多 Agent 手搓版）\n"
            f"Provider：{settings.provider_label}\n"
            f"模型：{settings.model}\n"
            f"工具来源：{'MCP server' if args.mcp else '进程内直连'}\n"
            "主 Agent：PlannerAgent\n"
            f"工具：{', '.join(agent.tool_names)}\n"
            "输入 /exit 退出；直接输入你的旅行需求即可。\n"
        )

        # prompt_toolkit 正确处理中文等宽字符的编辑/删除，也自带历史记录
        session = PromptSession()
        while True:
            try:
                line = session.prompt("你：").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue
            if line.lower() in EXIT_COMMANDS:
                break

            recorder = RunRecorder(line, metadata={"source": "cli"})
            agent.set_recorder(recorder)
            log.info("运行记录：%s", recorder.dir)

            try:
                result = agent.plan(line)
                recorder.finish(status="ok", result=result.model_dump(mode="json"))
                print()
                _print_trip(result, as_json=args.json)
                print()
            except Exception as exc:  # noqa: BLE001 - keep the REPL alive
                recorder.finish(status="error", error=traceback.format_exc())
                log.warning("请求失败：%s", exc)
                print(f"\n请求失败：{exc}\n", file=sys.stderr)
            finally:
                agent.set_recorder(None)

        return 0
    finally:
        if mcp_client is not None:
            mcp_client.stop()


def _print_trip(plan, *, as_json: bool) -> None:
    if as_json:
        print(plan.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    else:
        print(plan.to_markdown())


def _build_agent(
    settings: Settings,
    tool_overrides: dict[str, Any] | None = None,
) -> PlannerAgent:
    if settings.api_key is None:
        raise ValueError("缺少 API Key")

    log.debug(
        "构建 OpenAI 客户端：api_key=%s, base_url=%s",
        mask_secret(settings.api_key),
        settings.base_url or "OpenAI 默认",
    )
    if settings.base_url:
        client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    else:
        client = OpenAI(api_key=settings.api_key)

    return build_planner(
        client=client,
        model=settings.model,
        # Planner 要整合 3 个子 Agent 的结果，并逐段算交通，8 轮通常不够
        max_turns=max(settings.max_turns, 16),
        tool_overrides=tool_overrides,
    )

"""PlannerAgent：Plan-and-Resolve + Reflection。

流程：
1. Plan       先拆研究任务（ResearchPlan），不急着排行程。
2. Resolve    按计划并行查景点、天气、酒店。
3. Draft      根据计划 + 资料写一版 TripPlan 草稿。
4. Reflect    审查草稿，输出 ReflectionReport。
5. Revise     根据审阅意见修改，最多 max_reflection_rounds 轮。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, cast

from ..models import ReflectionReport, ResearchPlan, TripPlan
from ..runs import RunRecorder
from ..tools.amap import build_amap_route_tool
from ..tools.base import Tool, ToolRegistry
from ..tools.currency import build_currency_tool
from ..trace import get_logger
from .attraction import AttractionSearchAgent
from .base import Agent, EventSink
from .hotel import HotelAgent
from .weather import WeatherQueryAgent

log = get_logger("agents.planner")

PLAN_INSTRUCTIONS = """你是一个旅行研究规划师。你的任务不是直接排行程，而是先制定研究计划。

请把用户需求拆成「需要查证的任务」，并输出 ResearchPlan JSON：
- destination：目的地
- dates：日期范围（没有就 null）
- travelers：人数/同行人
- constraints：硬约束（非自驾、预算、天数、节奏、必须去/不想去等）
- tasks：研究任务列表，每项包含
  - kind：attraction / weather / hotel / transport / food / other
  - query：具体要查什么（例如“深圳湾公园、南头古城、华侨城创意园”）
  - reason：为什么需要它
  - priority：1-5，1 最高
- reflection_focus：后面反思时要重点检查的点
- summary：一句话研究策略

只输出 JSON。
"""

DRAFT_INSTRUCTIONS = (
    "你是一个旅行总规划师。请根据「研究计划」和「检索结果」"
    "输出一份完整、可执行的 TripPlan。\n\n"
    "要求：\n"
    "1. 按天分配景点，考虑地理邻近、开放时间、用餐时间和休息节奏。\n"
    "2. 非自驾时优先地铁/公交/步行；用 plan_route 计算关键路段（每天 1-2 段即可）。\n"
    "3. 酒店尽量固定，避免频繁搬行李；参考天气安排室内/室外。\n"
    "4. 需要外币预算时用 convert_currency。\n"
    "5. 输出 TripPlan JSON，days 是 DayPlan 列表，每天含 "
    "weather / attractions / meals / hotel / routes / notes。\n"
    "只输出 JSON。"
)

REFLECT_INSTRUCTIONS = (
    "你是一个严格的旅行行程审阅者。请审查行程草稿，"
    "找出与用户需求冲突、不可执行或不合理的地方。\n\n"
    "检查角度：\n"
    "- 节奏是否过满/过松\n"
    "- 景点之间交通是否可行，是否来回折返\n"
    "- 天气与室内外安排是否匹配\n"
    "- 酒店是否固定、是否靠近交通\n"
    "- 用餐时间/地点是否合理\n"
    "- 预算是否超支\n"
    "- 是否违反硬约束（非自驾、天数、起止日期等）\n\n"
    "输出 ReflectionReport JSON：\n"
    "- score：1-10\n"
    "- should_revise：是否需要修改\n"
    "- issues：每个问题包含 category / severity / description / suggestion\n"
    "- summary：一句话结论\n\n"
    "只输出 JSON。"
)


class PlannerAgent(Agent):
    def __init__(
        self,
        *,
        client,
        model: str,
        max_turns: int = 10,
        tools: list[Tool] | None = None,
        sub_tools: dict[str, list[Tool]] | None = None,
        event_sink: EventSink | None = None,
        recorder: RunRecorder | None = None,
        max_reflection_rounds: int = 2,
    ) -> None:
        sub = sub_tools or {}
        self._attraction = AttractionSearchAgent(
            client=client, model=model, tools=sub.get("attraction")
        )
        self._weather = WeatherQueryAgent(client=client, model=model, tools=sub.get("weather"))
        self._hotel = HotelAgent(client=client, model=model, tools=sub.get("hotel"))

        registry = ToolRegistry(tools or [build_amap_route_tool(), build_currency_tool()])
        self._max_reflection_rounds = max_reflection_rounds

        super().__init__(
            name="PlannerAgent",
            instructions=DRAFT_INSTRUCTIONS,
            registry=registry,
            model=model,
            client=client,
            max_turns=max_turns,
            output_model=TripPlan,
            event_sink=event_sink,
            recorder=recorder,
        )

        self._plan_agent = Agent(
            name="PlanAgent",
            instructions=PLAN_INSTRUCTIONS,
            registry=ToolRegistry([]),
            model=model,
            client=client,
            max_turns=2,
            output_model=ResearchPlan,
            event_sink=event_sink,
            recorder=recorder,
        )
        self._draft_agent = Agent(
            name="DraftPlannerAgent",
            instructions=DRAFT_INSTRUCTIONS,
            registry=registry,
            model=model,
            client=client,
            max_turns=max_turns,
            output_model=TripPlan,
            event_sink=event_sink,
            recorder=recorder,
        )
        self._reflect_agent = Agent(
            name="ReflectionAgent",
            instructions=REFLECT_INSTRUCTIONS,
            registry=ToolRegistry([]),
            model=model,
            client=client,
            max_turns=2,
            output_model=ReflectionReport,
            event_sink=event_sink,
            recorder=recorder,
        )

        if event_sink is not None:
            self.set_event_sink(event_sink)
        if recorder is not None:
            self.set_recorder(recorder)

    def set_event_sink(self, sink: EventSink | None) -> None:
        super().set_event_sink(sink)
        for agent in self._phase_agents():
            agent.set_event_sink(sink)

    def set_recorder(self, recorder: RunRecorder | None) -> None:
        super().set_recorder(recorder)
        for agent in self._phase_agents():
            agent.set_recorder(recorder)

    def _phase_agents(self) -> tuple[Agent, ...]:
        return (
            self._attraction,
            self._weather,
            self._hotel,
            self._plan_agent,
            self._draft_agent,
            self._reflect_agent,
        )

    def plan(self, user_request: str, event_sink: EventSink | None = None) -> TripPlan:
        if event_sink is not None:
            self.set_event_sink(event_sink)

        self._emit("plan_start", "开始制定研究计划")
        plan = cast(ResearchPlan, self._plan_agent.run_structured(self._plan_prompt(user_request)))
        self._emit(
            "plan_done",
            f"研究计划：{plan.summarize()}",
            destination=plan.destination,
            constraints=plan.constraints,
            tasks=[task.model_dump(mode="json") for task in plan.tasks],
        )

        self._emit("resolve_start", "开始按计划检索景点、天气、酒店")
        gathered = self._gather(user_request, plan)
        self._emit(
            "resolve_done",
            "资料检索完成，开始撰写行程草稿",
            results={key: _result_summary(value) for key, value in gathered.items()},
        )

        self._emit("draft_start", "开始撰写行程草稿")
        draft = cast(
            TripPlan,
            self._draft_agent.run_structured(self._draft_prompt(user_request, plan, gathered)),
        )
        self._emit("draft_done", f"草稿完成：{draft.summarize()}")

        for round_no in range(1, self._max_reflection_rounds + 1):
            self._emit("reflect_start", f"第 {round_no} 轮反思", round=round_no)
            report = cast(
                ReflectionReport,
                self._reflect_agent.run_structured(self._reflect_prompt(user_request, plan, draft)),
            )
            self._emit(
                "reflect_done",
                f"反思完成：{report.summarize()}",
                score=report.score,
                should_revise=report.should_revise,
                issues=[issue.model_dump(mode="json") for issue in report.issues],
            )

            if not report.should_revise or round_no == self._max_reflection_rounds:
                break

            self._emit("revise_start", f"根据第 {round_no} 轮反思修改行程", round=round_no)
            draft = cast(
                TripPlan,
                self._draft_agent.run_structured(self._revise_prompt(report)),
            )
            self._emit("revise_done", f"修改完成：{draft.summarize()}")

        return draft

    def _gather(self, user_request: str, plan: ResearchPlan) -> dict[str, Any]:
        tasks = {
            "景点": (self._attraction, self._sub_agent_input(plan, "attraction", user_request)),
            "天气": (self._weather, {"city": plan.destination}),
            "酒店": (self._hotel, self._sub_agent_input(plan, "hotel", user_request)),
        }

        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            future_to_key = {
                pool.submit(
                    agent.run_structured,
                    json.dumps(payload, ensure_ascii=False),
                ): key
                for key, (agent, payload) in tasks.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as exc:  # noqa: BLE001 - 单个子 Agent 失败不影响其他
                    log.warning("%s 查询失败：%s", key, exc)
                    results[key] = {"error": str(exc)}

        return results

    def _sub_agent_input(
        self,
        plan: ResearchPlan,
        kind: str,
        user_request: str,
    ) -> dict[str, Any]:
        queries = [task.query for task in plan.tasks if task.kind == kind]
        return {
            "city": plan.destination,
            "keywords": "；".join(queries) or user_request,
            "user_request": user_request,
            "constraints": plan.constraints,
        }

    def _plan_prompt(self, user_request: str) -> str:
        return (
            f"用户需求：{user_request}\n\n"
            "请先制定研究计划：想清楚要查哪些景点、天气、酒店、交通和餐饮，"
            "以及后面反思时要检查什么。只输出 ResearchPlan JSON。"
        )

    def _draft_prompt(
        self,
        user_request: str,
        plan: ResearchPlan,
        gathered: dict[str, Any],
    ) -> str:
        return (
            f"用户需求：{user_request}\n\n"
            f"研究计划：{_dump(plan)}\n\n"
            "以下是按计划检索到的资料：\n"
            f"【景点】{_dump(gathered['景点'])}\n"
            f"【天气】{_dump(gathered['天气'])}\n"
            f"【酒店】{_dump(gathered['酒店'])}\n\n"
            "请据此输出完整的 TripPlan JSON。"
        )

    def _reflect_prompt(
        self,
        user_request: str,
        plan: ResearchPlan,
        draft: TripPlan,
    ) -> str:
        return (
            f"用户需求：{user_request}\n\n"
            f"研究计划：{_dump(plan)}\n\n"
            f"行程草稿：{_dump(draft)}\n\n"
            "请严格审查这份行程，输出 ReflectionReport JSON。"
        )

    def _revise_prompt(self, report: ReflectionReport) -> str:
        return (
            "审阅意见如下：\n"
            f"{_dump(report)}\n\n"
            "请根据这些意见修改上一版行程，输出完整的 TripPlan JSON。"
        )


def build_planner(
    *,
    client,
    model: str,
    max_turns: int = 10,
    tool_overrides: dict[str, Tool] | None = None,
    event_sink: EventSink | None = None,
    recorder: RunRecorder | None = None,
    max_reflection_rounds: int = 2,
) -> PlannerAgent:
    """构建 PlannerAgent；传入 tool_overrides 时改用外部工具（例如 MCP）。"""

    if tool_overrides is None:
        return PlannerAgent(
            client=client,
            model=model,
            max_turns=max_turns,
            event_sink=event_sink,
            recorder=recorder,
            max_reflection_rounds=max_reflection_rounds,
        )

    return PlannerAgent(
        client=client,
        model=model,
        max_turns=max_turns,
        tools=[tool_overrides["plan_route"], tool_overrides["convert_currency"]],
        sub_tools={
            "attraction": [tool_overrides["search_poi"]],
            "weather": [tool_overrides["get_weather"]],
            "hotel": [tool_overrides["search_poi"]],
        },
        event_sink=event_sink,
        recorder=recorder,
        max_reflection_rounds=max_reflection_rounds,
    )


def _dump(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json(by_alias=True, exclude_none=True)
    return json.dumps(value, ensure_ascii=False)


def _result_summary(value: Any) -> str:
    if hasattr(value, "summarize"):
        return value.summarize()
    if isinstance(value, dict) and "error" in value:
        return f"失败：{value['error']}"
    return str(value)

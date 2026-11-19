"""FastAPI 后端：把旅行 Agent 暴露成 HTTP API。"""

from __future__ import annotations

import asyncio
import json
import traceback
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from ..agents.planner import PlannerAgent, build_planner
from ..config import Settings
from ..models import TripPlan
from ..runs import RunRecorder


class PlanRequest(BaseModel):
    """前端提交的旅行需求。"""

    prompt: str = Field(min_length=1, max_length=4000, description="用户的旅行需求")


app = FastAPI(
    title="Travel Agent API",
    version="0.1.0",
    description="多 Agent 旅行规划服务：景点、天气、酒店、路线、预算。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_planner() -> PlannerAgent:
    """依赖：为每次请求构建一个 PlannerAgent（无状态）。"""

    settings = Settings.from_env()
    if settings.api_key is None:
        raise HTTPException(status_code=500, detail="缺少 API Key，请检查 .env")

    if settings.base_url:
        client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    else:
        client = OpenAI(api_key=settings.api_key)

    return build_planner(
        client=client,
        model=settings.model,
        max_turns=max(settings.max_turns, 16),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict[str, str]:
    settings = Settings.from_env()
    return {
        "provider": settings.provider_label,
        "model": settings.model,
    }


@app.post("/api/plan", response_model=TripPlan)
def plan(
    request: PlanRequest,
    response: Response,
    planner: Annotated[PlannerAgent, Depends(get_planner)],
) -> TripPlan:
    """根据旅行需求生成完整行程。"""

    recorder = RunRecorder(request.prompt, metadata={"source": "api"})
    planner.set_recorder(recorder)
    response.headers["X-Run-Id"] = recorder.run_id

    try:
        trip = planner.plan(request.prompt)
    except Exception as exc:  # noqa: BLE001 - 把 Agent 错误转成 API 错误
        recorder.finish(status="error", error=traceback.format_exc())
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    recorder.finish(status="ok", result=trip.model_dump(mode="json"))
    return trip


@app.post("/api/plan/stream")
async def plan_stream(
    request: PlanRequest,
    planner: Annotated[PlannerAgent, Depends(get_planner)],
) -> StreamingResponse:
    """用 SSE 实时推送规划进度：子 Agent、工具调用、最终结果。"""

    recorder = RunRecorder(request.prompt, metadata={"source": "api"})
    planner.set_recorder(recorder)

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def sink(event: dict[str, Any]) -> None:
        # 子 Agent 在线程池里跑，必须用线程安全的方式写回事件循环
        recorder.event(event)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def worker() -> None:
        try:
            trip = await asyncio.to_thread(planner.plan, request.prompt, sink)
            data = trip.model_dump(mode="json")
            sink(
                {
                    "type": "done",
                    "run_id": recorder.run_id,
                    "message": "行程生成完成",
                    "data": data,
                }
            )
            recorder.finish(status="ok", result=data)
        except Exception as exc:  # noqa: BLE001 - 把异常变成前端可见的 error 事件
            sink({"type": "error", "run_id": recorder.run_id, "message": str(exc)})
            recorder.finish(status="error", error=traceback.format_exc())
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    sink(
        {
            "type": "run_started",
            "run_id": recorder.run_id,
            "message": f"运行记录：{recorder.run_id}",
        }
    )
    task = asyncio.create_task(worker())

    async def events():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue

                if event is None:
                    break

                yield (f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n")
        finally:
            task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

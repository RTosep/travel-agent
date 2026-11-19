"""每次运行的记录目录。

目录结构（runs/<run_id>/）：
- meta.json    运行元信息：prompt、模型、状态、耗时
- events.jsonl 每个 Agent/工具事件（与 SSE 推送一致）
- llm.jsonl    每次 LLM 请求和响应（含原始 content，排查坏 JSON 用）
- tools.jsonl  每次工具调用的完整参数和结果
- final.json   最终 TripPlan
- error.txt    失败时的异常堆栈
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunRecorder:
    def __init__(
        self,
        prompt: str,
        *,
        runs_dir: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        base = runs_dir or Path(os.environ.get("TRAVEL_AGENT_RUNS_DIR", PROJECT_ROOT / "runs"))
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.dir = base / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._closed = False
        self._started_at = _now()
        self._meta: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": self._started_at,
            "prompt": prompt,
            **(metadata or {}),
        }

        self._events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        self._llm = (self.dir / "llm.jsonl").open("a", encoding="utf-8")
        self._tools = (self.dir / "tools.jsonl").open("a", encoding="utf-8")
        self._write_json("meta.json", {**self._meta, "status": "running"})

    def event(self, event: dict[str, Any]) -> None:
        self._append(self._events, {"ts": _now(), "run_id": self.run_id, **event})

    def llm(self, payload: dict[str, Any]) -> None:
        self._append(self._llm, {"ts": _now(), **payload})

    def tool(self, payload: dict[str, Any]) -> None:
        self._append(self._tools, {"ts": _now(), **payload})

    def finish(
        self,
        *,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        if self._closed:
            return

        finished_at = _now()
        self._write_json(
            "meta.json",
            {
                **self._meta,
                "status": status,
                "finished_at": finished_at,
                "duration_seconds": _duration_seconds(self._started_at),
            },
        )
        if result is not None:
            self._write_json("final.json", result)
        if error:
            with self._lock:
                (self.dir / "error.txt").write_text(error, encoding="utf-8")

        self._closed = True
        self._close()

    def _append(self, handle, payload: dict[str, Any]) -> None:
        if self._closed:
            return

        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            handle.write(line + "\n")
            handle.flush()

    def _write_json(self, name: str, payload: Any) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        with self._lock:
            (self.dir / name).write_text(text, encoding="utf-8")

    def _close(self) -> None:
        with self._lock:
            for handle in (self._events, self._llm, self._tools):
                with contextlib.suppress(Exception):
                    handle.close()


def _duration_seconds(started_at: str) -> float:
    start = datetime.fromisoformat(started_at)
    return round((datetime.now().astimezone() - start).total_seconds(), 2)

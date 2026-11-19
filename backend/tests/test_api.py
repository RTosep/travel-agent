"""Tests for the HTTP API."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from travel_agent.api.app import app, get_planner
from travel_agent.models import TripPlan


class FakePlanner:
    def set_recorder(self, recorder) -> None:
        self.recorder = recorder

    def plan(self, prompt: str) -> TripPlan:
        return TripPlan(title=f"测试：{prompt}", destination="深圳", days=[])


class StreamingFakePlanner:
    def set_recorder(self, recorder) -> None:
        self.recorder = recorder

    def plan(self, prompt: str, event_sink=None) -> TripPlan:
        if event_sink is not None:
            event_sink({"type": "agent_start", "agent": "FakeAgent", "message": "开始"})
            event_sink({"type": "agent_result", "agent": "FakeAgent", "message": "完成"})
        return TripPlan(title=f"流式：{prompt}", destination="深圳", days=[])


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_plan_endpoint_returns_trip_plan() -> None:
    app.dependency_overrides[get_planner] = lambda: FakePlanner()
    try:
        client = TestClient(app)
        response = client.post("/api/plan", json={"prompt": "深圳三日"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "测试：深圳三日"
    assert data["destination"] == "深圳"
    assert data["days"] == []


def test_plan_stream_emits_progress_events() -> None:
    app.dependency_overrides[get_planner] = lambda: StreamingFakePlanner()
    try:
        client = TestClient(app)
        with client.stream("POST", "/api/plan/stream", json={"prompt": "深圳"}) as response:
            body = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: run_started" in body
    assert "event: agent_start" in body
    assert "event: agent_result" in body
    assert "event: done" in body
    assert "流式：深圳" in body


def test_plan_stream_writes_run_artifacts(tmp_path) -> None:
    app.dependency_overrides[get_planner] = lambda: StreamingFakePlanner()
    try:
        client = TestClient(app)
        with client.stream("POST", "/api/plan/stream", json={"prompt": "深圳"}) as response:
            body = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert "event: run_started" in body

    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "ok"
    assert meta["prompt"] == "深圳"

    final = json.loads((run_dir / "final.json").read_text(encoding="utf-8"))
    assert final["title"] == "流式：深圳"

    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(event["type"] == "agent_start" for event in events)


def test_plan_rejects_empty_prompt() -> None:
    client = TestClient(app)
    response = client.post("/api/plan", json={"prompt": ""})

    assert response.status_code == 422

"""Pytest 全局配置。"""

from __future__ import annotations

import pytest

import travel_agent.tools.amap as amap


@pytest.fixture(autouse=True)
def _reset_amap_state(monkeypatch):
    # 测试里不启用真实限速，并清空地理编码缓存，避免用例互相影响
    monkeypatch.setattr(amap, "_AMAP_MIN_INTERVAL", 0.0)
    amap._GEOCODE_CACHE.clear()


@pytest.fixture(autouse=True)
def _runs_dir(tmp_path, monkeypatch):
    # 运行记录写到临时目录，不污染项目的 runs/
    monkeypatch.setenv("TRAVEL_AGENT_RUNS_DIR", str(tmp_path / "runs"))

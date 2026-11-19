SHELL := /bin/bash

ROOT := $(CURDIR)
BACKEND := $(ROOT)/backend
FRONTEND := $(ROOT)/frontend

# 优先用系统 uv；没有就用项目内 uv（用绝对路径，cd 到 backend 后也能用）
UV ?= $(shell command -v uv 2>/dev/null || printf '%s' $(ROOT)/.tools/uv-venv/bin/uv)
UV_ENV := UV_CACHE_DIR=$(ROOT)/.tools/uv-cache UV_PYTHON_INSTALL_DIR=$(ROOT)/.tools/python

.PHONY: sync run trace mcp-run mcp-demo api web web-build dev test lint format check tools-check e2e

sync:
	cd $(BACKEND) && $(UV_ENV) $(UV) sync

run:
	cd $(BACKEND) && .venv/bin/travel-agent $(ARGS)

trace:
	cd $(BACKEND) && .venv/bin/travel-agent --trace $(ARGS)

mcp-run:
	cd $(BACKEND) && .venv/bin/travel-agent --mcp $(ARGS)

mcp-demo:
	cd $(BACKEND) && .venv/bin/python scripts/mcp_demo.py

api:
	cd $(BACKEND) && .venv/bin/uvicorn travel_agent.api.app:app --reload --port 8000

web:
	cd $(FRONTEND) && pnpm dev

web-build:
	cd $(FRONTEND) && pnpm build

dev:
	$(ROOT)/scripts/dev.sh

test:
	cd $(BACKEND) && .venv/bin/pytest

lint:
	cd $(BACKEND) && .venv/bin/ruff check .

format:
	cd $(BACKEND) && .venv/bin/ruff format .

tools-check:
	cd $(BACKEND) && .venv/bin/python scripts/check_tools.py

e2e:
	cd $(BACKEND) && .venv/bin/python scripts/e2e_mock.py

check: lint test

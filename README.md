# Travel Agent（Python 多 Agent + React 前端）

一个**前后端分离**的旅行规划应用：

- **后端**：Python + FastAPI + 手写多 Agent 循环（不依赖 LangChain / LangGraph / OpenAI Agents SDK）
- **前端**：React 19 + Vite + TypeScript + SCSS

默认使用 **DeepSeek**，也支持 OpenAI 或任何兼容 Chat Completions 的网关。

核心流程是 **Plan-and-Resolve + Reflection**：先拆研究任务，再并行检索景点/天气/酒店，
写完行程草稿后由 ReflectionAgent 审查，必要时修订，最后输出 `TripPlan`。

> 旧的 TypeScript 版本已移到 `../travel-agent-ts/`，仅作对照。

## 为什么手搓

| | 手搓 | 用框架 |
| --- | --- | --- |
| 控制流 | 每一行都可见 | 框架封装 |
| 学习价值 | 高 | 低一些 |
| 上手速度 | 慢一点 | 快 |
| 框架锁定 | 无 | 有 |
| 流式、重试、tracing、MCP | 要自己补 | 通常自带 |

这个版本适合：想理解 Agent 到底怎么跑、想完全控制行为、不想被框架抽象挡住。

它不是生产级实现。当前明确没有做：流式输出、并行工具调用、上下文裁剪、
重试/限流、持久化、tracing、MCP。这些正是框架帮你做的事，也是后续可以逐项补的。

## 技术栈

- Python 3.12（项目内隔离安装，不动系统 Python 3.9）
- `openai`：**只作为 Chat Completions 协议客户端**，可连 DeepSeek 或 OpenAI
- DeepSeek API：`https://api.deepseek.com`，OpenAI 格式兼容
- `fastapi` + `uvicorn`：后端 HTTP API
- React 19 + Vite + TypeScript + SCSS：前端页面
- `httpx`：调用天气、汇率和高德 API
- 高德地图 API：地理编码 / POI 搜索 / 路径规划（Web服务 Key）
- `mcp`：Model Context Protocol SDK（server + client，stdio 传输）
- `json-repair`：容错修复模型输出的非法 JSON
- `prompt-toolkit`：命令行交互式输入
- `pydantic`：领域模型 / 请求校验
- `python-dotenv`：读取 `.env`
- `pytest`：后端测试
- `ruff`：lint + format

## 快速开始

```bash
cd travel-agent
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 DEEPSEEK_API_KEY 和 AMAP_API_KEY
```

依赖已经安装在 `backend/.venv/`，直接运行：

```bash
backend/.venv/bin/travel-agent
```

或者用 Makefile：

```bash
make run
```

单次提问：

```bash
backend/.venv/bin/travel-agent "帮我规划 11 月中旬京都 5 天慢旅行，预算 1.2 万"
```

查看完整 trace（默认已打印关键步骤，`--trace` 更详细）：

```bash
backend/.venv/bin/travel-agent --trace "京都未来一周天气怎么样？"
```

### Web 页面（前后端分离）

```bash
make dev
```

- 前端：http://127.0.0.1:5173
- 后端 Swagger：http://127.0.0.1:8000/docs

也可以分开启动：

```bash
make api   # FastAPI :8000
make web   # Vite :5173
```

## 前后端分离

```text
frontend/ (React + Vite + TS)
   │  fetch  POST /api/plan/stream  { prompt }
   ▼  ← SSE: plan_done / resolve_done / draft_done / reflect_done / done
FastAPI (backend/travel_agent/api/app.py)
   │  PlannerAgent.plan(prompt, event_sink)
   ▼
Agents + Tools (Python)
   │  高德 / 汇率 / 天气
   ▼
TripPlan (JSON) ──► 前端渲染成攻略
```

职责划分：

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 前端 | `frontend/` | 输入需求、loading、错误处理、渲染 TripPlan |
| API | `backend/travel_agent/api/` | HTTP 路由、参数校验、CORS、调用 Agent |
| 领域 / Agent | `backend/travel_agent/agents/`、`tools/`、`models.py` | 业务逻辑，不关心 HTTP |

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 当前 provider / model |
| POST | `/api/plan` | 入参 `{"prompt": "..."}`，返回 `TripPlan` |
| POST | `/api/plan/stream` | 同上，但返回 SSE 实时进度 |
| GET | `/docs` | Swagger UI |

### 实时进度（SSE）

`POST /api/plan/stream` 返回 `text/event-stream`，服务端每完成一步就推送一个事件：

| 事件 | 含义 |
| --- | --- |
| `run_started` | 运行开始，带 `run_id` |
| `plan_start` / `plan_done` | 研究计划开始 / 完成 |
| `resolve_start` / `resolve_done` | 并行检索开始 / 完成 |
| `agent_start` | 某个子 Agent 开始处理 |
| `tool_call` / `tool_result` | 工具调用 / 调用完成 |
| `agent_result` | Agent 完成，带结果摘要 |
| `draft_start` / `draft_done` | 行程草稿开始 / 完成 |
| `reflect_start` / `reflect_done` | 反思开始 / 完成（带评分和问题数） |
| `revise_start` / `revise_done` | 根据反思修订行程 |
| `agent_retry` | 结构化输出不合法，自动重试 |
| `done` | 最终 `TripPlan`（在 `data` 字段里） |
| `error` | 失败原因 |

前端用 `fetch` 读取流并逐条渲染成时间线，用户能看到“正在做什么、刚完成什么、下一步是什么”。

页面默认只显示一条「当前阶段」摘要（例如“正在检索景点、天气、酒店”），
完整事件时间线收在「思考详情」按钮后面，点击才展开；主内容始终是最终攻略。

### 运行记录（backend/runs/）

每次 Web 请求或 CLI 运行都会在 `backend/runs/<run_id>/` 下写一份完整记录：

| 文件 | 内容 |
| --- | --- |
| `meta.json` | prompt、状态、开始/结束时间、耗时 |
| `events.jsonl` | 每个 Agent/工具事件（与 SSE 推送一致） |
| `llm.jsonl` | 每次 LLM 请求和响应（含原始 content） |
| `tools.jsonl` | 每次工具调用的完整参数和结果 |
| `final.json` | 最终 `TripPlan` |
| `error.txt` | 失败时的异常堆栈 |

SSE 的第一个事件 `run_started` 会带 `run_id`，前端时间线也会显示，方便直接定位到对应目录。

> 记录默认全部保留，单次约 100–200 KB；定期清理 `backend/runs/` 即可。

前端类型在 `frontend/src/types/`，字段与后端 `models.py` 对齐；后端启动后还可以访问
`/openapi.json`，后续可用 `openapi-typescript` 自动生成类型。

## 常用命令

```bash
make sync        # 重新同步依赖（使用项目内 uv + Python 3.12）
make run         # 进入交互模式（默认打印关键步骤）
make trace       # 进入交互模式，打印完整 trace（DEBUG）
make mcp-run     # 用 MCP server 跑完整 Agent
make mcp-demo    # MCP 握手 + 一次工具调用演示
make api         # 启动 FastAPI :8000
make web         # 启动 Vite :5173
make web-build   # 前端类型检查 + 生产构建
make dev         # 同时启动前后端
make test        # 运行测试
make lint        # ruff check
make format      # ruff format
make tools-check # 不调用模型，直接测试天气和汇率
make e2e         # 本地 mock 模型，验证 Plan→Resolve→Draft→Reflect→Revise
make check       # lint + test
```

如果不用 Makefile，直接调用：

```bash
cd backend
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format .
```

## 怎么看 trace

程序会用 [Python logging](https://docs.python.org/zh-cn/3/library/logging.html) 把每一步打印到 **stderr**，所以 **stdout 里只有模型的最终回答**，两者不会混在一起。

trace 分三档：

| 命令 | 级别 | 打印内容 |
| --- | --- | --- |
| `travel-agent`（默认） | INFO | 每个工具的结构化结果 + 最终回答 |
| `travel-agent --trace` / `make trace` | DEBUG | 再加：读取配置、循环轮次、请求 URL/参数等内部步骤 |
| `travel-agent --quiet` | WARNING | 关闭 trace，只留最终回答和错误 |

默认（INFO）只打印每个类的结构化结果，例如：

```text
[tools.registry] 工具 convert_currency [CurrencyConversion] → {"amount":100.0,"from":"CNY","to":"CNY","rate":1.0,...}
[tools.registry] 工具 get_weather [WeatherReport] → {"location":{...},"current":{...},"daily":[...]}
```

第三方 HTTP 客户端库的日志会被屏蔽。最终回答走 stdout，工具结果走 stderr，
两者不混。

> 安全：`api_key` 永远不会被完整打印，只显示开头和结尾（如 `sk-6…d8c0`）。

IDE 的 Python 解释器请选择：

```text
travel-agent/backend/.venv/bin/python
```

换一台机器时，先安装 [uv](https://docs.astral.sh/uv/)，然后执行 `make sync`。
uv 会根据 `backend/.python-version` 自动准备 Python 3.12，不需要手动安装 Python。

## 配置

配置文件：`backend/.env`（从 `backend/.env.example` 复制）。

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | 否 | 自动判断 | `deepseek` 或 `openai`；不填时按 Key 判断 |
| `DEEPSEEK_API_KEY` | DeepSeek 时是 | — | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek 的 OpenAI 兼容地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-flash` | 支持 tool calls；也可用 `deepseek-v4-pro` |
| `OPENAI_API_KEY` | OpenAI 时是 | — | OpenAI Key 或兼容网关的 Key |
| `OPENAI_BASE_URL` | 否 | OpenAI 官方 | 兼容 Chat Completions 的网关地址 |
| `OPENAI_MODEL` | 否 | `gpt-4o-mini` | 支持 function calling 的模型 |
| `AMAP_API_KEY` | 天气/POI/路线时是 | — | 高德开放平台「Web服务」Key |
| `AGENT_MAX_TURNS` | 否 | `8` | 最大模型调用轮数 |

> 这个版本用的是 **Chat Completions + function calling**，因此兼容性比
> Responses API 更广。只要网关支持 `tools` / `tool_calls` 就能用。

### 用 DeepSeek

```dotenv
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-flash
```

`deepseek-flash` 和 `deepseek-v4-pro` 都支持工具调用。DeepSeek 默认开启
thinking mode，响应里会带 `reasoning_content`；在使用 tools 的多轮对话中，
这个字段必须原样回传。本项目的 `message.model_dump()` 会保留它，并在后续请求
中一起发回，所以不需要额外处理。

参考：[DeepSeek API 文档](https://api-docs.deepseek.com/)、
[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)、
[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)。

### 用 OpenAI 或其他网关

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-gateway.example.com/v1
# OPENAI_MODEL=gpt-4o-mini
```

旧的三变量写法仍然可用：把 `OPENAI_API_KEY` 指向 DeepSeek Key，
`OPENAI_BASE_URL=https://api.deepseek.com`，`OPENAI_MODEL=deepseek-flash`。

## 目录结构

```text
travel-agent/
├── backend/                  # 后端服务（Python）
│   ├── travel_agent/
│   │   ├── agents/
│   │   │   ├── base.py        # Agent 基类 + 工具循环
│   │   │   ├── attraction.py  # AttractionSearchAgent
│   │   │   ├── weather.py     # WeatherQueryAgent
│   │   │   ├── hotel.py       # HotelAgent
│   │   │   └── planner.py     # PlannerAgent（Plan→Resolve→Draft→Reflect）
│   │   ├── api/
│   │   │   └── app.py         # FastAPI 接口 + SSE
│   │   ├── cli.py             # 命令行入口
│   │   ├── config.py          # 环境变量
│   │   ├── mcp/
│   │   │   ├── server.py      # MCP server（暴露高德/汇率工具）
│   │   │   └── client.py      # MCP client + Tool 适配器
│   │   ├── models.py          # 领域模型（Location → … → TripPlan）
│   │   ├── runs.py            # 运行记录器
│   │   └── tools/
│   │       ├── base.py        # Tool / ToolRegistry
│   │       ├── amap.py        # 高德：地理编码 / POI / 路径规划
│   │       ├── weather.py     # 高德天气
│   │       └── currency.py    # Frankfurter 汇率
│   ├── tests/
│   │   ├── test_agent_loop.py  # 用 fake client 测循环，不花 API 额度
│   │   ├── test_amap.py        # 用 httpx.MockTransport 测高德工具
│   │   ├── test_api.py         # FastAPI 接口测试
│   │   ├── test_mcp.py         # 测 MCP Tool 适配器
│   │   ├── test_models.py      # 测领域模型渲染
│   │   └── test_tools.py       # 用 httpx.MockTransport 测其余工具
│   ├── scripts/
│   │   ├── check_tools.py      # 不调用模型的工具冒烟测试
│   │   ├── e2e_mock.py         # 本地 mock 模型，验证完整 Pipeline
│   │   └── mcp_demo.py         # MCP 握手 + 工具调用演示
│   ├── runs/                   # 每次运行的记录（gitignore）
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version
│   ├── .env / .env.example
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── api/           # fetch / SSE 调用
│   │   ├── components/    # 每个组件一个文件夹：X.tsx + X.scss
│   │   ├── hooks/         # usePlanStream（页面状态）
│   │   ├── types/         # trip.ts / event.ts
│   │   ├── utils/         # format.ts / sse.ts / phase.ts
│   │   ├── App.tsx
│   │   ├── App.scss
│   │   ├── global.scss    # reset + 共享 .card
│   │   ├── _variables.scss
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── scripts/
│   └── dev.sh                # 同时启动前后端
├── .tools/                   # 项目内 uv + Python（gitignore）
├── Makefile
├── README.md
└── .gitignore
```

前端分层约定：

| 目录 | 职责 |
| --- | --- |
| `api/` | HTTP/SSE 通信，不写 UI |
| `hooks/` | 页面状态与副作用（loading / events / trip / error） |
| `components/X/` | 纯展示组件 + 该组件专属的 `X.scss`，不直接 fetch |
| `utils/` | 纯函数（格式化、SSE 解析） |
| `types/` | 与后端 `models.py` 对齐的类型 |

全局只保留 `global.scss`（reset + 共享 `.card`）和 `_variables.scss`；其余样式都跟着组件走。

## Plan-and-Resolve + Reflection

旅行规划不是“查到资料就直接排版”，而是先想清楚要查什么，查完再写、写完后反思、必要时修订。

```text
用户需求
  │
  ▼
PlanAgent（ResearchPlan）
  │  拆出：景点 / 天气 / 酒店 / 交通 / 餐饮 / 反思重点
  ▼
Resolve（ThreadPoolExecutor，并行）
  ├─ AttractionSearchAgent（search_poi）
  ├─ WeatherQueryAgent（get_weather）
  └─ HotelAgent（search_poi）
  ▼
DraftPlannerAgent（TripPlan 草稿，plan_route / convert_currency）
  ▼
ReflectionAgent（ReflectionReport：score / issues / should_revise）
  │
  ├─ 不需要修改 → 定稿
  └─ 需要修改 → DraftPlannerAgent 再改一版 → 再反思（最多 2 轮）
  ▼
TripPlan
```

阶段说明：

| 阶段 | Agent | 输出 | 作用 |
| --- | --- | --- | --- |
| Plan | `PlanAgent` | `ResearchPlan` | 先拆研究任务，避免盲目检索 |
| Resolve | 三个子 Agent | `AttractionSearchResult` / `WeatherReport` / `HotelSearchResult` | 按计划并行查资料 |
| Draft | `DraftPlannerAgent` | `TripPlan` | 把计划 + 资料写成行程 |
| Reflect | `ReflectionAgent` | `ReflectionReport` | 检查节奏、交通、天气、预算、约束 |
| Revise | `DraftPlannerAgent` | `TripPlan` | 根据审阅意见修订 |

每个 Agent 都有自己的 system prompt 和 Pydantic 输出模型：

| Agent | 职责 | 内部工具 | 输出模型 |
| --- | --- | --- | --- |
| `PlanAgent` | 拆研究任务 | 无 | `ResearchPlan` |
| `AttractionSearchAgent` | 搜景点、过滤地铁站/停车场等无关 POI | `search_poi` | `AttractionSearchResult` |
| `WeatherQueryAgent` | 查当前天气 + 4 天预报 | `get_weather` | `WeatherReport` |
| `HotelAgent` | 搜酒店、解析星级和每晚价格 | `search_poi` | `HotelSearchResult` |
| `DraftPlannerAgent` | 写/改行程 | `plan_route` + `convert_currency` | `TripPlan` |
| `ReflectionAgent` | 审查行程 | 无 | `ReflectionReport` |

编排入口仍然是 `PlannerAgent.plan()`；它负责按顺序串起这 5 个阶段，并把每个阶段的事件通过 SSE 推给前端。

### 最终输出

默认输出是给人看的 Markdown 攻略（标题、日期、预算、每天的景点/餐饮/酒店/交通/备注）。
需要机器可读的原始数据时加 `--json`：

```bash
travel-agent --json "深圳三日游"
```

## MCP 模式

项目内置了一个 MCP server（`mcp/server.py`），把高德/天气/汇率工具通过 **stdio** 暴露；
`mcp/client.py` 提供 `MCPClient` 和 `mcp_tool()` 适配器，把 MCP 工具转成项目里的 `Tool`。

交互流程（`make mcp-demo` 可以直接看到）：

```text
MCPClient.start()
  → 子进程 python -m travel_agent.mcp.server
  → initialize（握手，交换能力）
  → list_tools（拿到 search_poi / plan_route / get_weather / convert_currency）
  → call_tool(name, arguments)  （JSON-RPC over stdio）
  → 拿到 CallToolResult（文本 JSON）并解析
```

运行方式：

```bash
make mcp-demo   # 只演示 MCP 握手 + 一次工具调用（不消耗高德额度）
make mcp-run    # 用 MCP server 跑完整 Agent
# 或
backend/.venv/bin/travel-agent --mcp "深圳三日游"
```

> 注意：MCP 不会减少对高德 API 的请求。它只是把“进程内函数调用”换成“标准协议调用”。
> 真正减少请求的是地理编码缓存 + 全局限速 + QPS 重试（见上面的工具说明）。

## Agent 循环到底做了什么

每个 Agent（包括子 Agent）都复用 `agents/base.py` 里的同一个循环。
`Agent.run()` 的核心逻辑：

```python
self._messages.append({"role": "user", "content": prompt})

for _ in range(self._max_turns):
    response = self._client.chat.completions.create(
        model=self.model,
        messages=self._messages,
        tools=self._registry.specs(),
        tool_choice="auto",
    )

    message = response.choices[0].message
    self._messages.append(message.model_dump(exclude_none=True))

    if not message.tool_calls:
        return message.content

    for call in message.tool_calls:
        arguments = json.loads(call.function.arguments)
        result = self._registry.execute(call.function.name, arguments)
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            }
        )
```

就这四步：**问模型 → 拿到 tool_calls → 执行工具 → 把结果塞回消息列表**，
一直循环到模型不再调用工具。

> **结构化输出的容错**：`run_structured()` 会先严格解析 JSON；失败时用 `json-repair`
> 修复常见问题（少逗号、尾逗号、未转义字符），如果仍然校验失败，会自动让模型重试一次
> （SSE 里会出现 `agent_retry` 事件）。同时把 `max_tokens` 提到 8192，避免长行程 JSON
> 被截断。

## 工具

- `get_weather(city)`：高德地理编码（定位）+ 高德天气（当前 + 4 天预报）
- `search_poi(keywords, city, offset)`：高德 POI 搜索（景点/餐厅/酒店/商场）
- `plan_route(origin, destination, mode, city)`：高德路径规划（驾车/公交/步行/骑行）
- `convert_currency(amount, from, to)`：Frankfurter / 欧洲央行参考汇率，免费、无需 Key

> 高德针对**国内**地址、POI、天气效果最好，海外覆盖较弱。高德返回的是 GCJ-02（火星坐标），
> 本项目全程统一使用 GCJ-02。
>
> 高德个人 Key 有 QPS 限制，本项目内置了**全局限速（约 3 QPS）+ QPS 超限自动重试 +
> 地理编码缓存**，避免并行子 Agent 和连续路径规划把额度打爆。

工具内部返回的是 Pydantic 模型（见下面的领域模型），`ToolRegistry` 负责把它们
序列化成 JSON 再发给模型；工具抛异常、参数不合法、未知工具名，都会被转成
`{"error": "..."}` 返回给模型，而不是让整个进程崩掉。

新增工具只需要三步：

1. 写一个 handler，返回 Pydantic 模型或 `{"error": ...}` 字典
2. 用 Pydantic 定义参数模型
3. 用 `Tool(...)` 包装，加进 `build_travel_tools()`

## 领域模型

所有数据结构都定义在 [models.py](backend/travel_agent/models.py)，层次如下：

```text
Location             地点：名称、地址、经纬度、城市、区县、来源
 ├─ Poi              高德搜索的原始 POI（可用 classify() 归类）
 ├─ Attraction       景点：门票、开放时间、建议游玩时长、评分
 ├─ Meal             餐饮：餐次、菜系、人均、评分
 └─ Hotel            住宿：星级、每晚价格、入住/退房、评分

Route                交通：方式、起终点、距离、耗时
DailyWeather / WeatherReport
CurrencyConversion   汇率换算
Budget               预算拆分

DayPlan              某一天：天气 + 景点 + 餐饮 + 酒店 + 交通 + 备注
TripPlan             整趟：目的地 + 多个 DayPlan + 预算 + 概述
```

`Poi.classify()` 会根据高德分类自动把 POI 归为 `Attraction` / `Meal` / `Hotel`，
例如「风景名胜」→ 景点、「餐饮服务」→ 餐饮、「住宿服务」→ 酒店。

## 下一步可以加什么

1. **流式输出**：`stream=True`，边生成边打印
2. **并行工具调用**：多个 tool_calls 用线程池并发执行
3. **上下文管理**：超过 token 预算时裁剪旧消息或做摘要
4. **重试与限流**：对 429 / 5xx 做指数退避
5. **持久化**：把 messages 存 SQLite，支持跨会话恢复
6. **可观测性**：记录每轮 token、耗时、工具成功率
7. **MCP**：把地图、日历、Notion 封装成 MCP Server 再接入
8. **Web API**：用 FastAPI 包一层，前端就可以调用
9. **人工确认**：预订、支付等敏感工具先让用户确认

## 安全提醒

- `backend/.env` 已被 `.gitignore` 忽略，不要把真实 Key 提交到 Git。
- 汇率是参考值，实际支付以银行/支付平台为准。
- 签证、入境、安全、医疗信息请以目的地官方渠道为准。
- 不要让 Agent 在未经确认的情况下执行支付、预订或删除数据等不可逆操作。

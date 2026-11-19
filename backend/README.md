# Travel Agent Backend

后端服务：FastAPI + 多 Agent（Plan-and-Resolve + Reflection）。

启动、调试和接口说明见根目录 [`README.md`](../README.md)。常用命令（在仓库根目录执行）：

```bash
make sync     # 同步 Python 依赖（创建 backend/.venv）
make api      # 启动 FastAPI :8000
make run      # CLI（进程内工具）
make mcp-run  # CLI（MCP 模式）
make test     # pytest
```

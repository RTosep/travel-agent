"""Step-by-step tracing helpers for learning.

Logs are written to stderr so that stdout only carries the assistant's final
answer. API keys and other secrets are always masked before being logged.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "[%(name)s] %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a logger whose displayed name is short (e.g. "agent")."""

    return logging.getLogger(name)


def configure(level: int) -> None:
    """(Re)configure the root logger to print to stderr at the given level."""

    logging.basicConfig(
        level=level,
        format=_FORMAT,
        stream=sys.stderr,
        force=True,
    )

    # 屏蔽第三方 HTTP 客户端库的日志，只保留我们自己的日志
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def mask_secret(value: object | None, keep: int = 4) -> str:
    """Mask a secret so only its head and tail are visible."""

    if value is None:
        return "<未设置>"
    text = str(value).strip()
    if not text:
        return "<空>"
    if len(text) <= keep * 2:
        return f"{text[:keep]}…"
    return f"{text[:keep]}…{text[-keep:]}"


def truncate(value: object, limit: int = 200) -> str:
    """Shorten long text so the trace stays readable."""

    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…（共 {len(text)} 字符）"

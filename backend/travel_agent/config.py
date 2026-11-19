"""Environment-backed settings for OpenAI-compatible providers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .trace import get_logger, mask_secret

log = get_logger("config")

# Prefer the project's .env even when the console script is launched elsewhere;
# fall back to python-dotenv's normal current-directory search.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

PLACEHOLDER_KEY = "sk-your-key-here"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"
OPENAI_MODEL = "gpt-4o-mini"


@dataclass(frozen=True, slots=True)
class Settings:
    provider: str
    api_key: str | None
    base_url: str | None
    model: str
    max_turns: int

    @property
    def provider_label(self) -> str:
        return "DeepSeek" if self.provider == "deepseek" else "OpenAI"

    @classmethod
    def from_env(cls) -> Settings:
        log.debug("========== 读取配置 ==========")
        provider = _resolve_provider()

        if provider == "deepseek":
            raw_key = os.getenv("DEEPSEEK_API_KEY")
            api_key = _clean_key(raw_key)
            base_url = os.getenv("DEEPSEEK_BASE_URL", "").strip() or DEEPSEEK_BASE_URL
            model = os.getenv("DEEPSEEK_MODEL", "").strip() or DEEPSEEK_MODEL
            log.debug("provider = deepseek")
            log.debug("DEEPSEEK_API_KEY = %s", mask_secret(raw_key))
            log.debug("DEEPSEEK_BASE_URL = %s", base_url)
            log.debug("DEEPSEEK_MODEL = %s", model)
        else:
            raw_key = os.getenv("OPENAI_API_KEY")
            api_key = _clean_key(raw_key)
            base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
            model = os.getenv("OPENAI_MODEL", "").strip() or OPENAI_MODEL
            log.debug("provider = openai")
            log.debug("OPENAI_API_KEY = %s", mask_secret(raw_key))
            log.debug("OPENAI_BASE_URL = %s", base_url or "OpenAI 默认")
            log.debug("OPENAI_MODEL = %s", model)

        max_turns = _positive_int(os.getenv("AGENT_MAX_TURNS"), default=8)
        log.debug("AGENT_MAX_TURNS = %d", max_turns)
        log.debug("api_key 是否有效 = %s", "是" if api_key else "否（空或占位符）")
        log.debug("AMAP_API_KEY = %s", mask_secret(os.getenv("AMAP_API_KEY")))
        log.debug("==================================")
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_turns=max_turns,
        )


def _resolve_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit in {"deepseek", "openai"}:
        log.debug("LLM_PROVIDER 显式指定为 %s", explicit)
        return explicit

    if _clean_key(os.getenv("DEEPSEEK_API_KEY")):
        log.debug("未显式指定 provider；检测到 DEEPSEEK_API_KEY → 选择 DeepSeek")
        return "deepseek"

    log.debug("未显式指定 provider；未检测到 DEEPSEEK_API_KEY → 回退 OpenAI")
    return "openai"


def _clean_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key or key == PLACEHOLDER_KEY:
        return None
    return key


def _positive_int(raw: str | None, *, default: int) -> int:
    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    return value if value > 0 else default

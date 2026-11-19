"""Currency conversion tool backed by Frankfurter / ECB reference rates."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..models import CurrencyConversion
from ..trace import get_logger
from .base import Tool

log = get_logger("tools.currency")

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
USER_AGENT = "travel-agent-handrolled/0.1"


class CurrencyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    amount: float = Field(gt=0, description="要换算的金额，必须大于 0")
    from_currency: str = Field(
        alias="from",
        pattern=r"^[A-Za-z]{3}$",
        description="源货币代码，例如 CNY",
    )
    to_currency: str = Field(
        alias="to",
        pattern=r"^[A-Za-z]{3}$",
        description="目标货币代码，例如 JPY",
    )


def build_currency_tool() -> Tool:
    return Tool(
        name="convert_currency",
        description=(
            "按最新参考汇率换算货币，用于旅行预算、购物和跨境支付估算。"
            "货币使用 ISO 4217 三字母代码，例如 CNY、JPY、USD、EUR。"
        ),
        parameters=CurrencyArgs.model_json_schema(by_alias=True),
        handler=_handle_currency,
    )


def _handle_currency(args: dict[str, Any]) -> CurrencyConversion | dict[str, Any]:
    parsed = CurrencyArgs.model_validate(args)
    return convert_currency(
        parsed.amount,
        parsed.from_currency,
        parsed.to_currency,
    )


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    *,
    client: httpx.Client | None = None,
) -> CurrencyConversion | dict[str, Any]:
    base = from_currency.upper()
    quote = to_currency.upper()
    log.debug("convert_currency 入参：%s %s → %s", amount, base, quote)

    if amount <= 0:
        log.warning("金额必须大于 0")
        return {"error": "金额必须大于 0。"}

    if base == quote:
        log.debug("源货币 == 目标货币，无需请求接口")
        return CurrencyConversion(
            amount=amount,
            from_currency=base,
            to_currency=quote,
            rate=1,
            converted=amount,
            source="无需换算",
        )

    owns_client = client is None
    http = client or httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT})
    log.debug(
        "使用 %s", "新建的 httpx.Client（超时 15s）" if owns_client else "调用方传入的 httpx.Client"
    )

    try:
        params = {"base": base, "symbols": quote}
        log.debug("GET %s params=%s", FRANKFURTER_URL, params)
        response = http.get(FRANKFURTER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return {"error": "汇率接口返回了意外的数据格式。"}

        rates = data.get("rates")
        rate = rates.get(quote) if isinstance(rates, dict) else None
        if not isinstance(rate, (int, float)):
            log.warning("接口未返回 %s 的汇率", quote)
            return {"error": f"暂不支持 {base} → {quote} 的汇率。"}

        converted = round(amount * rate, 2)
        log.debug("汇率 rate=%s，换算结果=%s", rate, converted)

        return CurrencyConversion(
            amount=amount,
            from_currency=base,
            to_currency=quote,
            rate=rate,
            converted=converted,
            date=data.get("date"),
            source="Frankfurter（欧洲央行参考汇率）",
            note="参考汇率，实际支付以银行或支付平台为准。",
        )
    except httpx.HTTPStatusError as exc:
        log.warning("汇率接口返回 HTTP %s", exc.response.status_code)
        return {"error": f"汇率接口返回 HTTP {exc.response.status_code}，请确认货币代码。"}
    except httpx.HTTPError as exc:
        log.warning("汇率接口请求失败：%s", exc)
        return {"error": f"汇率接口请求失败：{exc}"}
    except (TypeError, ValueError) as exc:
        log.warning("汇率数据解析失败：%s", exc)
        return {"error": f"汇率数据解析失败：{exc}"}
    finally:
        if owns_client:
            http.close()

"""Exercise the travel tools without spending model tokens."""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from travel_agent.tools.currency import convert_currency
from travel_agent.tools.weather import get_weather

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _dump(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(by_alias=True, exclude_none=True, mode="json")
    return json.dumps(value, ensure_ascii=False, indent=2)


def main() -> None:
    weather = get_weather("北京")
    print("天气工具：")
    print(_dump(weather))

    currency = convert_currency(1000, "CNY", "JPY")
    print("\n汇率工具：")
    print(_dump(currency))


if __name__ == "__main__":
    main()

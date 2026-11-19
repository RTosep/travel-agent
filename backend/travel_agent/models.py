"""领域模型：从最基础的地点，到整趟旅行。

层次结构：

    Location
      ├── Poi          （高德搜索的原始结果，可 classify 成下面三类）
      ├── Attraction   （景点）
      ├── Meal         （餐饮）
      └── Hotel        （住宿）

    DayPlan             （某一天：景点 + 餐饮 + 酒店 + 交通 + 天气）
    TripPlan            （整趟旅行：多个 DayPlan + 预算）

辅助结构：

    Route               （两点之间的交通方案）
    WeatherReport       （天气）
    CurrencyConversion  （汇率换算）
    Budget              （预算拆分）
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Location(BaseModel):
    """一个地点，是所有地点类别的基类。"""

    name: str = Field(description="地点名称")
    address: str | None = Field(default=None, description="详细地址")
    city: str | None = Field(default=None, description="所在城市")
    district: str | None = Field(default=None, description="所在区县")
    adcode: str | None = Field(default=None, description="行政区划编码")
    longitude: float | None = Field(default=None, description="经度（GCJ-02 火星坐标）")
    latitude: float | None = Field(default=None, description="纬度（GCJ-02 火星坐标）")
    source: str | None = Field(default=None, description="数据来源，例如“高德地图”")

    def summarize(self) -> str:
        return self.name or self.address or "未知地点"


class Poi(Location):
    """通用 POI，是 search_poi 的原始结果，尚未被归类。"""

    category: str | None = Field(default=None, description="高德分类，例如“风景名胜”“餐饮服务”")
    rating: float | None = Field(default=None, description="评分")
    avg_cost: float | None = Field(default=None, description="人均消费/票价（元）")
    telephone: str | None = Field(default=None, description="电话")

    def summarize(self) -> str:
        base = self.name or self.address or "未知"
        if self.rating is not None:
            return f"{base}（{self.rating}分）"
        return base

    def classify(self) -> Attraction | Meal | Hotel:
        """根据高德分类，把 POI 归为景点 / 餐饮 / 酒店。"""

        base = self.model_dump(
            include={
                "name",
                "address",
                "city",
                "district",
                "adcode",
                "longitude",
                "latitude",
                "source",
            }
        )
        category = self.category or ""

        if any(key in category for key in ("餐饮", "餐厅", "美食", "咖啡", "酒吧", "小吃")):
            return Meal(
                **base,
                cuisine=category or None,
                price_per_person=self.avg_cost,
                rating=self.rating,
            )

        if any(key in category for key in ("住宿", "酒店", "宾馆", "旅馆", "民宿")):
            return Hotel(
                **base,
                price_per_night=self.avg_cost,
                rating=self.rating,
            )

        return Attraction(
            **base,
            category=category or None,
            ticket_price=self.avg_cost,
            rating=self.rating,
        )


class PoiSearchResult(BaseModel):
    """一次 POI 搜索的结果。"""

    count: int = Field(default=0, description="总条数")
    pois: list[Poi] = Field(default_factory=list, description="POI 列表")

    def summarize(self) -> str:
        if not self.pois:
            return "0 条结果"
        head = "、".join(p.summarize() for p in self.pois[:3])
        tail = "…" if len(self.pois) > 3 else ""
        return f"{self.count} 条：{head}{tail}"


class Attraction(Location):
    """景点。"""

    rating: float | None = Field(default=None, description="评分")
    ticket_price: float | None = Field(default=None, description="门票价格（元）")
    opening_hours: str | None = Field(default=None, description="开放时间")
    category: str | None = Field(default=None, description="景点类型，例如“博物馆”“公园”")
    recommended_minutes: int | None = Field(default=None, description="建议游玩时长（分钟）")
    note: str | None = Field(default=None, description="备注")

    def summarize(self) -> str:
        text = self.name or "未知景点"
        if self.rating is not None:
            text += f"（{self.rating}分）"
        if self.ticket_price is not None:
            text += f"，门票{self.ticket_price}元"
        return text


class Meal(Location):
    """一顿饭 / 一家餐厅。"""

    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = Field(
        default=None, description="餐次：早餐/午餐/晚餐/小吃"
    )
    cuisine: str | None = Field(default=None, description="菜系，例如“川菜”“日料”")
    price_per_person: float | None = Field(default=None, description="人均消费（元）")
    rating: float | None = Field(default=None, description="评分")
    note: str | None = Field(default=None, description="备注")

    def summarize(self) -> str:
        text = self.name or "未知餐厅"
        if self.meal_type:
            text += f"（{self.meal_type}）"
        if self.price_per_person is not None:
            text += f"，人均{self.price_per_person}元"
        return text


class Hotel(Location):
    """住宿。"""

    star: int | None = Field(default=None, description="星级")
    price_per_night: float | None = Field(default=None, description="每晚价格（元）")
    check_in: str | None = Field(default=None, description="入住时间，例如 14:00")
    check_out: str | None = Field(default=None, description="退房时间，例如 12:00")
    rating: float | None = Field(default=None, description="评分")
    note: str | None = Field(default=None, description="备注")

    def summarize(self) -> str:
        text = self.name or "未知酒店"
        if self.star is not None:
            text += f"（{self.star}星）"
        if self.price_per_night is not None:
            text += f"，{self.price_per_night}元/晚"
        return text


class Route(BaseModel):
    """两点之间的交通方案。"""

    mode: Literal["driving", "transit", "walking", "bicycling"] = Field(description="出行方式")
    origin: Location = Field(description="起点")
    destination: Location = Field(description="终点")
    distance_km: float | None = Field(default=None, description="距离（公里）")
    duration_min: float | None = Field(default=None, description="耗时（分钟）")

    def summarize(self) -> str:
        parts = [self.mode, f"{self.origin.name} → {self.destination.name}"]
        if self.distance_km is not None:
            parts.append(f"{self.distance_km}km")
        if self.duration_min is not None:
            parts.append(f"{self.duration_min}min")
        return "，".join(parts)


class CurrentWeather(BaseModel):
    """当前天气。"""

    time: str | None = Field(default=None, description="观测时间")
    weather: str | None = Field(default=None, description="天气")
    temperature_c: float | None = Field(default=None, description="气温（℃）")
    humidity: str | None = Field(default=None, description="湿度")
    wind_direction: str | None = Field(default=None, description="风向")
    wind_power: str | None = Field(default=None, description="风力")


class DailyWeather(BaseModel):
    """某一天的天气预报。"""

    date: str | None = Field(default=None, description="日期，YYYY-MM-DD")
    weather: str | None = Field(default=None, description="天气描述")
    high_c: float | None = Field(default=None, description="最高温（℃）")
    low_c: float | None = Field(default=None, description="最低温（℃）")
    rain_chance_percent: int | None = Field(default=None, description="降雨概率（%）")


class WeatherReport(BaseModel):
    """一个城市的天气报告。"""

    location: Location = Field(description="地点")
    current: CurrentWeather | None = Field(default=None, description="当前天气")
    daily: list[DailyWeather] = Field(default_factory=list, description="未来几天预报")
    weather_source: str = "高德地图"
    geocode_source: str = "高德地图"

    def summarize(self) -> str:
        now = f"{self.current.weather} {self.current.temperature_c}℃" if self.current else "无实况"
        return f"{self.location.name} 当前 {now}；未来 {len(self.daily)} 天"


class CurrencyConversion(BaseModel):
    """货币换算结果。"""

    model_config = ConfigDict(populate_by_name=True)

    amount: float = Field(description="换算金额")
    from_currency: str = Field(alias="from", description="源货币代码")
    to_currency: str = Field(alias="to", description="目标货币代码")
    rate: float = Field(description="汇率")
    converted: float = Field(description="换算结果")
    date: str | None = Field(default=None, description="汇率日期")
    source: str | None = Field(default=None, description="数据来源")
    note: str | None = Field(default=None, description="备注")

    def summarize(self) -> str:
        return (
            f"{self.amount} {self.from_currency} → "
            f"{self.converted} {self.to_currency}（汇率 {self.rate}）"
        )


class Budget(BaseModel):
    """预算拆分。"""

    total: float | None = Field(default=None, description="总预算")
    transport: float | None = Field(default=None, description="交通")
    hotel: float | None = Field(default=None, description="住宿")
    meals: float | None = Field(default=None, description="餐饮")
    tickets: float | None = Field(default=None, description="门票")
    other: float | None = Field(default=None, description="其他")
    currency: str = Field(default="CNY", description="币种")


def _format_weather(weather: DailyWeather | None) -> str | None:
    if weather is None:
        return None

    parts: list[str] = []
    if weather.weather:
        parts.append(weather.weather)
    if weather.high_c is not None or weather.low_c is not None:
        high = f"{weather.high_c:g}" if weather.high_c is not None else "?"
        low = f"{weather.low_c:g}" if weather.low_c is not None else "?"
        parts.append(f"{low}~{high}℃")
    if weather.rain_chance_percent is not None:
        parts.append(f"降雨 {weather.rain_chance_percent}%")

    return "，".join(parts) or None


class DayPlan(BaseModel):
    """某一天的行程。"""

    day: int = Field(description="第几天，从 1 开始")
    date: Date | None = Field(default=None, description="具体日期")
    title: str | None = Field(default=None, description="当天主题，例如“老城慢游”")
    weather: DailyWeather | None = Field(default=None, description="当天天气")
    attractions: list[Attraction] = Field(default_factory=list, description="景点")
    meals: list[Meal] = Field(default_factory=list, description="餐饮")
    hotel: Hotel | None = Field(default=None, description="当晚住宿")
    routes: list[Route] = Field(default_factory=list, description="当天的交通")
    notes: list[str] = Field(default_factory=list, description="备注/提醒")

    def summarize(self) -> str:
        title = f" · {self.title}" if self.title else ""
        return f"第{self.day}天{title}：{len(self.attractions)}景点、{len(self.meals)}餐"

    def to_markdown(self) -> str:
        heading = f"## 第 {self.day} 天"
        if self.title:
            heading += f" · {self.title}"
        if self.date:
            heading += f"（{self.date.isoformat()}）"

        lines = [heading, ""]
        weather = _format_weather(self.weather)
        if weather:
            lines.append(f"- 天气：{weather}")
        if self.attractions:
            lines.append("- 景点：")
            lines.extend(f"  - {item.summarize()}" for item in self.attractions)
        if self.meals:
            lines.append("- 餐饮：")
            lines.extend(f"  - {item.summarize()}" for item in self.meals)
        if self.hotel:
            lines.append(f"- 住宿：{self.hotel.summarize()}")
        if self.routes:
            lines.append("- 交通：")
            lines.extend(f"  - {item.summarize()}" for item in self.routes)
        if self.notes:
            lines.append("- 备注：")
            lines.extend(f"  - {note}" for note in self.notes)

        return "\n".join(lines)


class TripPlan(BaseModel):
    """整趟旅行。"""

    title: str = Field(description="旅行标题")
    destination: str | None = Field(default=None, description="目的地")
    start_date: Date | None = Field(default=None, description="开始日期")
    end_date: Date | None = Field(default=None, description="结束日期")
    days: list[DayPlan] = Field(default_factory=list, description="每天的计划")
    budget: Budget | None = Field(default=None, description="预算")
    summary: str | None = Field(default=None, description="整体概述")

    def summarize(self) -> str:
        dest = f" · {self.destination}" if self.destination else ""
        return f"{self.title}{dest}：{len(self.days)} 天"

    def to_markdown(self) -> str:
        header = [f"# {self.title}", ""]
        if self.destination:
            header.append(f"- 目的地：{self.destination}")
        if self.start_date or self.end_date:
            start = self.start_date.isoformat() if self.start_date else "?"
            end = self.end_date.isoformat() if self.end_date else "?"
            header.append(f"- 日期：{start} ~ {end}")
        if self.budget:
            header.append(f"- 预算：{self._budget_line()}")
        if self.summary:
            header.append(f"- 概述：{self.summary}")

        sections = ["\n".join(header).rstrip()]
        if self.days:
            sections.extend(day.to_markdown() for day in self.days)
        else:
            sections.append("（暂无每日安排）")

        return "\n\n".join(sections)

    def _budget_line(self) -> str:
        budget = self.budget
        if budget is None:
            return "未提供"

        parts: list[str] = []
        if budget.total is not None:
            parts.append(f"总 {budget.total:g} {budget.currency}")
        for label, value in (
            ("交通", budget.transport),
            ("住宿", budget.hotel),
            ("餐饮", budget.meals),
            ("门票", budget.tickets),
            ("其他", budget.other),
        ):
            if value is not None:
                parts.append(f"{label} {value:g}")

        return "，".join(parts) or "未提供"


class ResearchTask(BaseModel):
    """Plan 阶段拆出来的一条研究任务。"""

    kind: Literal["attraction", "weather", "hotel", "transport", "food", "other"]
    query: str = Field(description="具体要查什么")
    reason: str | None = Field(default=None, description="为什么要查")
    priority: int = Field(default=3, ge=1, le=5, description="优先级，1 最高")


class ResearchPlan(BaseModel):
    """Plan 阶段的输出：先想清楚要研究什么，再去查。"""

    destination: str = Field(description="目的地")
    dates: str | None = Field(default=None, description="日期范围")
    travelers: str | None = Field(default=None, description="人数/同行人")
    constraints: list[str] = Field(default_factory=list, description="硬约束（非自驾、预算等）")
    tasks: list[ResearchTask] = Field(default_factory=list, description="研究任务")
    reflection_focus: list[str] = Field(default_factory=list, description="反思阶段重点检查什么")
    summary: str | None = Field(default=None, description="一句话研究策略")

    def summarize(self) -> str:
        return f"{self.destination}：{len(self.tasks)} 个研究任务"


class ReflectionIssue(BaseModel):
    """反思阶段发现的一个问题。"""

    category: Literal[
        "pace",
        "route",
        "weather",
        "budget",
        "hotel",
        "meal",
        "opening_hours",
        "constraint",
        "other",
    ]
    severity: Literal["low", "medium", "high"]
    description: str
    suggestion: str


class ReflectionReport(BaseModel):
    """Reflection 阶段的输出。"""

    score: int = Field(ge=1, le=10, description="行程质量评分")
    should_revise: bool = Field(description="是否需要修改")
    issues: list[ReflectionIssue] = Field(default_factory=list)
    summary: str | None = None

    def summarize(self) -> str:
        return f"{self.score}/10，{len(self.issues)} 个问题"


class AttractionSearchResult(BaseModel):
    """景点搜索子 Agent 的输出。"""

    attractions: list[Attraction] = Field(default_factory=list, description="景点列表")

    def summarize(self) -> str:
        if not self.attractions:
            return "0 个景点"
        head = "、".join(a.summarize() for a in self.attractions[:3])
        tail = "…" if len(self.attractions) > 3 else ""
        return f"{len(self.attractions)} 个景点：{head}{tail}"


class HotelSearchResult(BaseModel):
    """酒店搜索子 Agent 的输出。"""

    hotels: list[Hotel] = Field(default_factory=list, description="酒店列表")

    def summarize(self) -> str:
        if not self.hotels:
            return "0 家酒店"
        head = "、".join(h.summarize() for h in self.hotels[:3])
        tail = "…" if len(self.hotels) > 3 else ""
        return f"{len(self.hotels)} 家酒店：{head}{tail}"


def classify_poi(poi: Poi) -> Attraction | Meal | Hotel:
    """把 POI 归类为景点 / 餐饮 / 酒店（便捷函数）。"""

    return poi.classify()


__all__ = [
    "Attraction",
    "AttractionSearchResult",
    "Budget",
    "CurrencyConversion",
    "CurrentWeather",
    "DailyWeather",
    "DayPlan",
    "Hotel",
    "HotelSearchResult",
    "Location",
    "Meal",
    "Poi",
    "PoiSearchResult",
    "ReflectionIssue",
    "ReflectionReport",
    "ResearchPlan",
    "ResearchTask",
    "Route",
    "TripPlan",
    "WeatherReport",
    "classify_poi",
]

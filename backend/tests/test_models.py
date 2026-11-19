"""Tests for domain model rendering."""

from __future__ import annotations

from datetime import date

from travel_agent.models import (
    Attraction,
    Budget,
    DailyWeather,
    DayPlan,
    Hotel,
    Location,
    Meal,
    Route,
    TripPlan,
)


def test_trip_plan_to_markdown_contains_key_sections() -> None:
    day = DayPlan(
        day=1,
        date=date(2026, 11, 9),
        title="老城漫游",
        weather=DailyWeather(
            date="2026-11-09",
            weather="晴",
            high_c=25.0,
            low_c=15.0,
        ),
        attractions=[Attraction(name="深圳湾公园", rating=4.9, ticket_price=0.0)],
        meals=[Meal(name="海鲜餐厅", meal_type="lunch", price_per_person=120.0)],
        hotel=Hotel(name="深圳湾酒店", star=5, price_per_night=800.0),
        routes=[
            Route(
                mode="transit",
                origin=Location(name="酒店"),
                destination=Location(name="深圳湾公园"),
                distance_km=6.57,
                duration_min=24.3,
            )
        ],
        notes=["记得带防晒"],
    )
    trip = TripPlan(
        title="深圳三日",
        destination="深圳",
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 11),
        days=[day],
        budget=Budget(total=3000.0),
    )

    markdown = trip.to_markdown()

    assert "# 深圳三日" in markdown
    assert "目的地：深圳" in markdown
    assert "2026-11-09 ~ 2026-11-11" in markdown
    assert "第 1 天 · 老城漫游" in markdown
    assert "深圳湾公园" in markdown
    assert "海鲜餐厅" in markdown
    assert "深圳湾酒店" in markdown
    assert "6.57km" in markdown
    assert "预算" in markdown

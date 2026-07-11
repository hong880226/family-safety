"""Dashboard summary schemas."""
from datetime import date
from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    today_minutes: int
    week_minutes: int
    overtime_count_this_week: int
    top_apps: list[dict]
    last_quiz_at: str | None = None
    current_streak_days: int = 0
    used_vs_limit_percent: float


class UsageSummaryOut(BaseModel):
    date: date
    total_minutes: int
    by_app: list[dict]
    by_category: dict

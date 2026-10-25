from datetime import date, datetime

from pydantic import BaseModel


class DailyClickCount(BaseModel):
    date: date
    count: int


class LinkAnalyticsResponse(BaseModel):
    short_code: str
    total_clicks: int
    last_clicked_at: datetime | None
    clicks_over_time: list[DailyClickCount]

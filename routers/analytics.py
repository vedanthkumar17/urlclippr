from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.analytics import DailyClickCount, LinkAnalyticsResponse
from services.analytics import get_click_summary, get_clicks_by_day
from services.shortener import get_link_by_short_code

router = APIRouter()


@router.get(
    "/links/{short_code}/analytics",
    response_model=LinkAnalyticsResponse,
)
def get_link_analytics(
    short_code: str,
    db: Session = Depends(get_db),
) -> LinkAnalyticsResponse:
    link = get_link_by_short_code(db, short_code)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found.",
        )

    total_clicks, last_clicked_at = get_click_summary(db, link.id)
    clicks_by_day = get_clicks_by_day(db, link.id)

    return LinkAnalyticsResponse(
        short_code=link.short_code,
        total_clicks=total_clicks,
        last_clicked_at=last_clicked_at,
        clicks_over_time=[
            DailyClickCount(date=click_date, count=count)
            for click_date, count in clicks_by_day
        ],
    )

from datetime import date, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from models.click import ClickEvent


def get_click_summary(
    db: Session,
    link_id: int,
) -> tuple[int, datetime | None]:
    total_clicks, last_clicked_at = db.execute(
        select(
            func.count(ClickEvent.id),
            func.max(ClickEvent.clicked_at),
        ).where(ClickEvent.link_id == link_id)
    ).one()

    return total_clicks, last_clicked_at


def get_clicks_by_day(
    db: Session,
    link_id: int,
) -> list[tuple[date, int]]:
    click_day = cast(func.timezone("UTC", ClickEvent.clicked_at), Date)

    rows = db.execute(
        select(
            click_day.label("date"),
            func.count(ClickEvent.id).label("count"),
        )
        .where(ClickEvent.link_id == link_id)
        .group_by(click_day)
        .order_by(click_day)
    ).all()

    return [(row.date, row.count) for row in rows]

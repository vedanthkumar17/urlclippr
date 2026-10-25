import secrets
import string

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from models.click import ClickEvent
from models.link import Link

ALPHABET = string.ascii_letters + string.digits
MAX_CODE_ATTEMPTS = 5


class ShortCodeGenerationError(Exception):
    pass


def generate_short_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def get_link_by_short_code(db: Session, short_code: str) -> Link | None:
    return db.scalar(select(Link).where(Link.short_code == short_code))


def record_click(db: Session, link_id: int) -> ClickEvent:
    click_event = ClickEvent(link_id=link_id)
    db.add(click_event)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return click_event


def create_short_link(db: Session, original_url: str) -> Link:
    for _ in range(MAX_CODE_ATTEMPTS):
        link = Link(
            short_code=generate_short_code(),
            original_url=original_url,
        )
        db.add(link)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue

        db.refresh(link)
        return link

    raise ShortCodeGenerationError("Could not generate a unique short code.")

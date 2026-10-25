from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.link import LinkCreate, LinkResponse
from services.shortener import ShortCodeGenerationError, create_short_link

router = APIRouter()


@router.post("/links", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: LinkCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> LinkResponse:
    original_url = str(payload.url)

    try:
        link = create_short_link(db, original_url)
    except ShortCodeGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    short_url = f"{str(request.base_url).rstrip('/')}/{link.short_code}"

    return LinkResponse(
        original_url=link.original_url,
        short_code=link.short_code,
        short_url=short_url,
    )

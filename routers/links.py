from fastapi import APIRouter, Request

from schemas.link import LinkCreate, LinkResponse
from services.shortener import create_short_link

router = APIRouter()


@router.post("/links", response_model=LinkResponse, status_code=201)
def create_link(payload: LinkCreate, request: Request) -> LinkResponse:
    original_url = str(payload.url)
    short_code = create_short_link(original_url)

    short_url = f"{str(request.base_url).rstrip('/')}/{short_code}"

    return LinkResponse(
        original_url=original_url,
        short_code=short_code,
        short_url=short_url,
    )

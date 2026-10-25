import secrets
import string

from fastapi import APIRouter, Request
from pydantic import BaseModel, HttpUrl

router = APIRouter()

links: dict[str, str] = {}

ALPHABET = string.ascii_letters + string.digits


class LinkCreate(BaseModel):
    url: HttpUrl


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str


def generate_short_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


@router.post("/links", response_model=LinkResponse, status_code=201)
def create_link(payload: LinkCreate, request: Request) -> LinkResponse:
    short_code = generate_short_code()

    while short_code in links:
        short_code = generate_short_code()

    original_url = str(payload.url)
    links[short_code] = original_url

    short_url = f"{str(request.base_url).rstrip('/')}/{short_code}"

    return LinkResponse(
        original_url=original_url,
        short_code=short_code,
        short_url=short_url,
    )

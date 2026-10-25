from pydantic import BaseModel, HttpUrl


class LinkCreate(BaseModel):
    url: HttpUrl


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str

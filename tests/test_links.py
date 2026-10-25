import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from database import Base, DATABASE_URL, engine, get_db
from main import app
from models.link import Link
from services import shortener


@pytest.fixture
def test_database():
    schema_name = f"test_{uuid.uuid4().hex}"

    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    test_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={
            "options": f"-csearch_path={schema_name} -c timezone=UTC",
        },
    )
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    try:
        yield TestSessionLocal
    finally:
        test_engine.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))


@pytest.fixture
def client(test_database):
    def override_get_db():
        db = test_database()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_link_persists_to_database(client, test_database):
    response = client.post(
        "/links",
        json={"url": "https://example.com/some/path"},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"original_url", "short_code", "short_url"}
    assert body["original_url"] == "https://example.com/some/path"
    assert len(body["short_code"]) == 6
    assert body["short_code"].isalnum()
    assert body["short_url"] == f"http://testserver/{body['short_code']}"

    with test_database() as db:
        link = db.scalar(select(Link).where(Link.short_code == body["short_code"]))

    assert link is not None
    assert link.original_url == body["original_url"]
    assert link.created_at.tzinfo is not None
    assert link.created_at.utcoffset() == timedelta(0)


def test_redirects_to_original_url(client):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/redirect-target"},
    )
    short_code = create_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/redirect-target"


def test_unknown_short_code_returns_404(client):
    response = client.get("/doesnotexist", follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"detail": "Short code not found."}


def test_invalid_url_is_rejected(client, test_database):
    response = client.post("/links", json={"url": "not-a-url"})

    assert response.status_code == 422

    with test_database() as db:
        link_count = db.scalar(select(func.count()).select_from(Link))

    assert link_count == 0


def test_short_codes_are_unique(client, test_database):
    short_codes = set()

    for index in range(25):
        response = client.post(
            "/links",
            json={"url": f"https://example.com/page/{index}"},
        )

        assert response.status_code == 201
        short_codes.add(response.json()["short_code"])

    assert len(short_codes) == 25

    with test_database() as db:
        link_count = db.scalar(select(func.count()).select_from(Link))

    assert link_count == 25


def test_short_code_collision_is_retried(client, test_database, monkeypatch):
    first_response = client.post(
        "/links",
        json={"url": "https://example.com/first"},
    )
    existing_code = first_response.json()["short_code"]
    replacement_code = "Z9z9Z9" if existing_code != "Z9z9Z9" else "Y8y8Y8"

    generated_codes = iter([existing_code, replacement_code])
    monkeypatch.setattr(shortener, "generate_short_code", lambda: next(generated_codes))

    response = client.post(
        "/links",
        json={"url": "https://example.com/second"},
    )

    assert response.status_code == 201
    assert response.json()["short_code"] == replacement_code

    with test_database() as db:
        links = db.scalars(select(Link).order_by(Link.id)).all()

    assert [link.short_code for link in links] == [existing_code, replacement_code]
    assert links[1].created_at.tzinfo is not None
    assert links[1].created_at <= datetime.now(timezone.utc)

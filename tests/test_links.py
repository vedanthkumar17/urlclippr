import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from database import Base, DATABASE_URL, engine, get_db
from main import app
from models.click import ClickEvent
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


def test_valid_redirect_records_one_click_event(client, test_database):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/click-target"},
    )
    short_code = create_response.json()["short_code"]

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/click-target"

    with test_database() as db:
        link_id = db.scalar(select(Link.id).where(Link.short_code == short_code))
        clicks = db.scalars(select(ClickEvent).where(ClickEvent.link_id == link_id)).all()

    assert len(clicks) == 1
    assert clicks[0].link_id == link_id
    assert clicks[0].clicked_at.tzinfo is not None
    assert clicks[0].clicked_at.utcoffset() == timedelta(0)


def test_multiple_redirects_record_multiple_click_events(client, test_database):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/multiple-clicks"},
    )
    short_code = create_response.json()["short_code"]

    for _ in range(3):
        response = client.get(f"/{short_code}", follow_redirects=False)
        assert response.status_code == 302

    with test_database() as db:
        link_id = db.scalar(select(Link.id).where(Link.short_code == short_code))
        click_count = db.scalar(
            select(func.count())
            .select_from(ClickEvent)
            .where(ClickEvent.link_id == link_id)
        )

    assert click_count == 3


def test_invalid_short_code_records_no_click_event(client, test_database):
    response = client.get("/doesnotexist", follow_redirects=False)

    assert response.status_code == 404

    with test_database() as db:
        click_count = db.scalar(select(func.count()).select_from(ClickEvent))

    assert click_count == 0


def test_creating_link_records_no_click_event(client, test_database):
    response = client.post(
        "/links",
        json={"url": "https://example.com/no-click-on-create"},
    )

    assert response.status_code == 201

    with test_database() as db:
        click_count = db.scalar(select(func.count()).select_from(ClickEvent))

    assert click_count == 0


def test_redirect_still_works_when_click_recording_fails(
    client,
    test_database,
    monkeypatch,
):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/click-failure"},
    )
    short_code = create_response.json()["short_code"]

    def fail_to_record_click(db, link_id):
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr("routers.links.record_click", fail_to_record_click)

    response = client.get(f"/{short_code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/click-failure"

    with test_database() as db:
        click_count = db.scalar(select(func.count()).select_from(ClickEvent))

    assert click_count == 0


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


def test_analytics_for_link_with_zero_clicks(client):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/no-analytics-yet"},
    )
    short_code = create_response.json()["short_code"]

    response = client.get(f"/links/{short_code}/analytics")

    assert response.status_code == 200
    assert response.json() == {
        "short_code": short_code,
        "total_clicks": 0,
        "last_clicked_at": None,
        "clicks_over_time": [],
    }


def test_analytics_unknown_short_code_returns_404(client):
    response = client.get("/links/doesnotexist/analytics")

    assert response.status_code == 404
    assert response.json() == {"detail": "Short code not found."}


def test_analytics_counts_redirect_visits(client):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/analytics-visits"},
    )
    short_code = create_response.json()["short_code"]

    for _ in range(2):
        redirect_response = client.get(f"/{short_code}", follow_redirects=False)
        assert redirect_response.status_code == 302

    response = client.get(f"/links/{short_code}/analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["short_code"] == short_code
    assert body["total_clicks"] == 2
    assert body["last_clicked_at"] is not None
    last_clicked_at = datetime.fromisoformat(
        body["last_clicked_at"].replace("Z", "+00:00")
    )
    assert last_clicked_at.utcoffset() == timedelta(0)
    assert sum(item["count"] for item in body["clicks_over_time"]) == 2


def test_analytics_groups_clicks_by_utc_day(client, test_database):
    create_response = client.post(
        "/links",
        json={"url": "https://example.com/analytics-days"},
    )
    short_code = create_response.json()["short_code"]

    with test_database() as db:
        link_id = db.scalar(select(Link.id).where(Link.short_code == short_code))
        db.add_all(
            [
                ClickEvent(
                    link_id=link_id,
                    clicked_at=datetime(2026, 1, 2, 20, 0, tzinfo=timezone.utc),
                ),
                ClickEvent(
                    link_id=link_id,
                    clicked_at=datetime(
                        2026,
                        1,
                        3,
                        4,
                        30,
                        tzinfo=timezone(timedelta(hours=5, minutes=30)),
                    ),
                ),
                ClickEvent(
                    link_id=link_id,
                    clicked_at=datetime(2026, 1, 3, 1, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()

    response = client.get(f"/links/{short_code}/analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_clicks"] == 3
    assert body["clicks_over_time"] == [
        {"date": "2026-01-02", "count": 2},
        {"date": "2026-01-03", "count": 1},
    ]
    assert datetime.fromisoformat(
        body["last_clicked_at"].replace("Z", "+00:00")
    ) == datetime(2026, 1, 3, 1, 0, tzinfo=timezone.utc)

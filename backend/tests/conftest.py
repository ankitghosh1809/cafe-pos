"""
Shared pytest fixtures.

These tests run against a REAL Postgres database (set via DATABASE_URL),
not a mock — this app leans on Postgres-specific features (JSONB, partial
unique indexes, window functions) that an in-memory/SQLite stand-in
wouldn't exercise honestly. Locally: point DATABASE_URL at a scratch
database before running `pytest` (see README → Running tests). In CI, the
GitHub Actions workflow spins up a real Postgres service container.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cafepos_test")
os.environ.setdefault("OWNER_PASSWORD", "testowner123")
os.environ.setdefault("STAFF_PASSWORD", "teststaff123")
os.environ.setdefault("SECRET_KEY", "pytest-secret-not-for-prod")

import pytest
import psycopg2
import app as flask_app_module


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    """init_db() already ran once at import time (module top level); this
    just confirms the connection is actually alive before any test runs, so
    a misconfigured DATABASE_URL fails fast with a clear error instead of
    forty confusing individual test failures."""
    conn = psycopg2.connect(flask_app_module._db_url())
    conn.close()
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    """Every test starts from a known-empty state (fresh categories/menu
    items/orders), so tests don't leak state into each other regardless of
    run order. TRUNCATE ... CASCADE also clears order_items/discount_requests
    /reviews via their FK relationships."""
    conn = psycopg2.connect(flask_app_module._db_url())
    cur = conn.cursor()
    cur.execute("TRUNCATE categories, menu_items, orders, table_servers, reviews RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
    flask_app_module._menu_cache_clear()
    yield


@pytest.fixture
def client():
    flask_app_module.app.config["TESTING"] = True
    with flask_app_module.app.test_client() as c:
        yield c


@pytest.fixture
def owner_token(client):
    res = client.post("/api/owner/login", json={"password": "testowner123"})
    return res.get_json()["token"]


@pytest.fixture
def staff_token(client):
    res = client.post("/api/staff/login", json={"password": "teststaff123"})
    return res.get_json()["token"]


@pytest.fixture
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def make_menu_item(client, owner_headers):
    """Factory fixture: make_menu_item(price=140, modifiers=[...]) -> item dict."""
    cat = client.post(
        "/api/menu/items", headers=owner_headers,
        json={"category_id": _ensure_category(), "name": "Test Item", "price": 100},
    )

    def _make(name="Test Item", price=100, available=1, modifiers=None):
        res = client.post(
            "/api/menu/items", headers=owner_headers,
            json={
                "category_id": _ensure_category(), "name": name, "price": price,
                "available": available, "modifiers": modifiers,
            },
        )
        assert res.status_code == 201, res.get_json()
        return res.get_json()

    return _make


def _ensure_category():
    """Menu items need a category_id FK; tests share one throwaway category
    created directly against the DB (cheaper than going through the API,
    and category CRUD isn't what these tests are about)."""
    conn = psycopg2.connect(flask_app_module._db_url())
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories LIMIT 1")
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]
    cur.execute("INSERT INTO categories(name, icon) VALUES('Test Category','☕') RETURNING id")
    cat_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return cat_id

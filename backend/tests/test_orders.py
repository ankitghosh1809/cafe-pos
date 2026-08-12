"""Order lifecycle: access control (IDOR fixes) and the one-open-tab-per-table guarantee."""
import psycopg2
import pytest
import app as flask_app_module


def test_legacy_create_order_endpoint_is_gone(client):
    res = client.post("/api/orders", json={"items": [{"item_id": 1, "quantity": 1, "unit_price": 1}]})
    assert res.status_code == 405


def test_get_single_order_requires_owner(client, make_menu_item, owner_headers):
    item = make_menu_item(price=100)
    order = client.post("/api/tables/T1/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    assert client.get(f"/api/orders/{order['id']}").status_code == 401
    assert client.get(f"/api/orders/{order['id']}", headers=owner_headers).status_code == 200


def test_receipt_requires_its_own_token(client, make_menu_item, owner_headers):
    item = make_menu_item(price=100)
    order = client.post("/api/tables/T2/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    client.post("/api/tables/T2/pay", json={"payment_method": "cash"})

    assert client.get(f"/api/orders/{order['id']}/receipt").status_code == 404
    assert client.get(f"/api/orders/{order['id']}/receipt?token=wrong-token").status_code == 404
    good = client.get(f"/api/orders/{order['id']}/receipt?token={order['receipt_token']}")
    assert good.status_code == 200
    # owner can always view it, no token needed
    assert client.get(f"/api/orders/{order['id']}/receipt", headers=owner_headers).status_code == 200


def test_receipt_ids_are_not_sequentially_guessable_across_tables(client, make_menu_item):
    """Not a test of ID unpredictability (they're still SERIAL) — a test
    that knowing the ID alone is no longer sufficient, which is the actual
    fix (see test_receipt_requires_its_own_token)."""
    item = make_menu_item(price=100)
    o1 = client.post("/api/tables/T3/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    o2 = client.post("/api/tables/T4/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    assert o1["receipt_token"] != o2["receipt_token"]


def test_only_one_open_order_per_table_at_db_level(client, make_menu_item):
    """Deterministic version of the concurrency guarantee: attempting to
    directly INSERT a second 'open' order for a table that already has one
    must fail at the database level, regardless of how the request got
    there. (The API itself never does this — see add_items_to_tab, which
    reuses the existing open order — this test locks in the safety net.)"""
    item = make_menu_item(price=100)
    client.post("/api/tables/T5/items", json={"items": [{"item_id": item["id"], "quantity": 1}]})

    conn = psycopg2.connect(flask_app_module._db_url())
    cur = conn.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("INSERT INTO orders(table_no, status) VALUES('T5', 'open')")
    conn.rollback()
    conn.close()


def test_placing_order_twice_reuses_the_same_tab(client, make_menu_item):
    item = make_menu_item(price=100)
    o1 = client.post("/api/tables/T6/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    o2 = client.post("/api/tables/T6/items", json={"items": [{"item_id": item["id"], "quantity": 1}]}).get_json()
    assert o1["id"] == o2["id"]
    assert len(o2["items"]) == 2

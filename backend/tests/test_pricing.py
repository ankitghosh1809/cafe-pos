"""
Regression tests for the price-tampering fix.

An earlier version of add_items_to_tab() trusted a client-supplied
unit_price for every line item. These tests exist to make sure that never
comes back: whatever price/discount a request claims, the server must
always charge the price it looks up from menu_items itself.
"""
import pytest


def test_normal_order_charges_the_real_price(client, make_menu_item):
    item = make_menu_item(name="Latte", price=140)
    res = client.post("/api/tables/T1/items", json={"items": [{"item_id": item["id"], "quantity": 2}]})
    assert res.status_code == 201
    body = res.get_json()
    assert body["items"][0]["unit_price"] == 140
    assert body["subtotal"] == 280


def test_tampered_unit_price_is_ignored(client, make_menu_item):
    """The core exploit: item costs 140, attacker claims it costs 1."""
    item = make_menu_item(name="Latte", price=140)
    res = client.post(
        "/api/tables/T2/items",
        json={"items": [{"item_id": item["id"], "quantity": 1, "unit_price": 1}]},
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["items"][0]["unit_price"] == 140, "client-supplied unit_price must never be used"
    assert body["subtotal"] == 140


def test_tampered_zero_price_is_ignored(client, make_menu_item):
    item = make_menu_item(name="Latte", price=140)
    res = client.post(
        "/api/tables/T3/items",
        json={"items": [{"item_id": item["id"], "quantity": 1, "unit_price": 0}]},
    )
    assert res.get_json()["items"][0]["unit_price"] == 140


def test_tampered_modifier_delta_is_ignored(client, make_menu_item):
    """Same exploit via the modifiers path: item's real 'Large' option adds
    30, attacker claims it should subtract 1000."""
    item = make_menu_item(name="Cappuccino", price=140, modifiers=[
        {"name": "Size", "type": "single", "required": True,
         "options": [{"label": "Regular", "delta": 0}, {"label": "Large", "delta": 30}]},
    ])
    res = client.post(
        "/api/tables/T4/items",
        json={"items": [{
            "item_id": item["id"], "quantity": 1,
            "modifiers": [{"group": "Size", "option": "Large", "delta": -1000}],
        }]},
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["items"][0]["unit_price"] == 170, "server's own +30 delta must be used, not the client's -1000"


def test_required_modifier_must_be_chosen(client, make_menu_item):
    item = make_menu_item(name="Cappuccino", price=140, modifiers=[
        {"name": "Size", "type": "single", "required": True,
         "options": [{"label": "Regular", "delta": 0}, {"label": "Large", "delta": 30}]},
    ])
    res = client.post("/api/tables/T5/items", json={"items": [{"item_id": item["id"], "quantity": 1}]})
    assert res.status_code == 400
    assert "Size" in res.get_json()["error"]


def test_unknown_modifier_option_rejected(client, make_menu_item):
    item = make_menu_item(name="Cappuccino", price=140, modifiers=[
        {"name": "Size", "type": "single", "required": True,
         "options": [{"label": "Regular", "delta": 0}]},
    ])
    res = client.post(
        "/api/tables/T6/items",
        json={"items": [{"item_id": item["id"], "quantity": 1, "modifiers": [{"group": "Size", "option": "Extra Large"}]}]},
    )
    assert res.status_code == 400


def test_unavailable_item_cannot_be_ordered(client, make_menu_item):
    item = make_menu_item(name="Sold Out Cake", price=200, available=0)
    res = client.post("/api/tables/T7/items", json={"items": [{"item_id": item["id"], "quantity": 1}]})
    assert res.status_code == 400
    assert "unavailable" in res.get_json()["error"]


def test_nonexistent_item_rejected(client):
    res = client.post("/api/tables/T8/items", json={"items": [{"item_id": 999999, "quantity": 1}]})
    assert res.status_code == 400


def test_negative_quantity_rejected(client, make_menu_item):
    item = make_menu_item(price=100)
    res = client.post("/api/tables/T9/items", json={"items": [{"item_id": item["id"], "quantity": -5}]})
    assert res.status_code == 400


def test_tax_and_discount_math(client, make_menu_item, owner_headers):
    """subtotal 200 -> 5% tax = 10 -> 10% discount on subtotal = 20 -> total = 200 + 10 - 20 = 190."""
    item = make_menu_item(price=200)
    client.post("/api/tables/T10/items", json={"items": [{"item_id": item["id"], "quantity": 1}]})
    req = client.post("/api/tables/T10/discount-request", json={})
    req_id = req.get_json()["id"]
    client.post(f"/api/discount-requests/{req_id}/resolve", headers=owner_headers,
                json={"action": "approve", "discount_percent": 10})
    tab = client.get("/api/tables/T10/tab").get_json()["order"]
    assert tab["subtotal"] == 200
    assert tab["tax"] == 10
    assert tab["discount"] == 20
    assert tab["total"] == 190

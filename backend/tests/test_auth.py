"""Tests for the owner/staff auth boundary and token integrity."""


def test_owner_login_wrong_password_rejected(client):
    res = client.post("/api/owner/login", json={"password": "not-the-password"})
    assert res.status_code == 401


def test_owner_login_correct_password_issues_token(client):
    res = client.post("/api/owner/login", json={"password": "testowner123"})
    assert res.status_code == 200
    assert "token" in res.get_json()


def test_owner_route_rejects_no_token(client):
    res = client.get("/api/reports/sales")
    assert res.status_code == 401


def test_owner_route_rejects_tampered_token(client, owner_token):
    tampered = owner_token[:-4] + "AAAA"
    res = client.get("/api/reports/sales", headers={"Authorization": f"Bearer {tampered}"})
    assert res.status_code == 401


def test_staff_token_cannot_reach_owner_only_routes(client, staff_token):
    headers = {"Authorization": f"Bearer {staff_token}"}
    for method, path in [
        ("GET", "/api/reports/sales"),
        ("GET", "/api/reports/order-history"),
        ("GET", "/api/discount-requests"),
        ("GET", "/api/reviews"),
        ("POST", "/api/menu/items"),
        ("GET", "/api/orders/1"),
    ]:
        res = client.open(path, method=method, headers=headers, json={})
        assert res.status_code == 401, f"staff token should not reach {method} {path}"


def test_staff_token_can_reach_kitchen(client, staff_token):
    res = client.get("/api/kitchen/queue", headers={"Authorization": f"Bearer {staff_token}"})
    assert res.status_code == 200


def test_owner_token_also_works_on_staff_routes(client, owner_token):
    res = client.get("/api/kitchen/queue", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200


def test_staff_login_wrong_password_rejected(client):
    res = client.post("/api/staff/login", json={"password": "wrong"})
    assert res.status_code == 401

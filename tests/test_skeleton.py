def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_user_header_is_401(client):
    r = client.get("/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_blank_user_header_is_401(client):
    r = client.get("/me", headers={"X-User-Id": "   "})
    assert r.status_code == 401


def test_user_header_is_used(client):
    r = client.get("/me", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "alice"}


def test_unknown_route_uses_error_shape(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

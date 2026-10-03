from fastapi.testclient import TestClient

from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app())


def test_health():
    r = client().get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_user_header_is_401():
    r = client().get("/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_blank_user_header_is_401():
    r = client().get("/me", headers={"X-User-Id": "   "})
    assert r.status_code == 401


def test_user_header_is_used():
    r = client().get("/me", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "alice"}


def test_unknown_route_uses_error_shape():
    r = client().get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

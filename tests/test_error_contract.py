"""Every error, whatever its cause, must use {"error": {"code": ..., "message": ...}}."""
import pytest

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}

# (name, method, path, headers, json, expected status, expected code)
CASES = [
    ("no header", "GET", "/me", {}, None, 401, "unauthorized"),
    ("blank header", "GET", "/channels", {"X-User-Id": " "}, None, 401, "unauthorized"),
    ("unknown route", "GET", "/nope", ALICE, None, 404, "not_found"),
    ("unknown channel", "GET", "/channels/999/messages", ALICE, None, 404, "not_found"),
    ("unknown message", "PATCH", "/messages/999", ALICE, {"body": "x"}, 404, "not_found"),
    ("missing reaction", "DELETE", "/messages/1/reactions?emoji=%F0%9F%94%A5", BOB, None, 404, "not_found"),
    ("not the author", "PATCH", "/messages/1", BOB, {"body": "x"}, 403, "forbidden"),
    ("duplicate channel", "POST", "/channels", ALICE, {"name": "general"}, 409, "conflict"),
    ("archived channel", "POST", "/channels/2/messages", ALICE, {"body": "x"}, 409, "conflict"),
    ("duplicate reaction", "POST", "/messages/1/reactions", BOB, {"emoji": "x1"}, 409, "conflict"),
    ("missing field", "POST", "/channels", ALICE, {}, 422, "validation_error"),
    ("bad path id", "POST", "/channels/abc/archive", ALICE, None, 422, "validation_error"),
    ("bad query value", "GET", "/channels/1/messages?limit=0", ALICE, None, 422, "validation_error"),
    ("reply to a reply", "POST", "/messages/2/replies", ALICE, {"body": "x"}, 422, "validation_error"),
    ("wrong method", "DELETE", "/health", ALICE, None, 405, "http_error"),
]


@pytest.fixture
def world(client):
    """Channel 1 'general' holding message 1 (alice) with reply 2 (bob) and an 'x1' reaction
    from bob on message 1, plus channel 2 'old', which is archived."""
    client.post("/channels", json={"name": "general"}, headers=ALICE)
    client.post("/channels", json={"name": "old"}, headers=ALICE)
    client.post("/channels/1/messages", json={"body": "hello"}, headers=ALICE)
    client.post("/messages/1/replies", json={"body": "reply"}, headers=BOB)
    client.post("/messages/1/reactions", json={"emoji": "x1"}, headers=BOB)
    client.post("/channels/2/archive", headers=ALICE)
    return client


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_error_response_shape_and_status(world, case):
    _, method, path, headers, body, status, code = case
    r = world.request(method, path, headers=headers, json=body)
    assert r.status_code == status
    assert r.headers["content-type"].startswith("application/json")
    payload = r.json()
    assert list(payload) == ["error"]
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


def test_validation_errors_list_the_offending_fields(world):
    r = world.post("/channels", json={"name": "bad name"}, headers=ALICE)
    details = r.json()["error"]["details"]
    assert [d["field"] for d in details] == ["name"]
    assert isinstance(details[0]["message"], str)

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}


def make(client, name="general", headers=ALICE):
    return client.post("/channels", json={"name": name}, headers=headers)


def test_create_channel(client):
    r = make(client)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "general"
    assert body["created_by"] == "alice"
    assert body["archived"] is False
    assert body["archived_at"] is None


def test_create_requires_user_header(client):
    r = client.post("/channels", json={"name": "general"})
    assert r.status_code == 401


def test_duplicate_name_is_409_even_with_different_case(client):
    assert make(client).status_code == 201
    r = make(client, "GENERAL", BOB)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_invalid_names_are_422(client):
    for bad in ["", "   ", "has space", "-leading", "x" * 81, "emoji😀"]:
        r = make(client, bad)
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "validation_error"


def test_missing_name_is_422(client):
    r = client.post("/channels", json={}, headers=ALICE)
    assert r.status_code == 422


def test_name_is_trimmed(client):
    assert make(client, "  random  ").json()["name"] == "random"


def test_list_channels_sorted_by_name(client):
    make(client, "zebra")
    make(client, "alpha")
    r = client.get("/channels", headers=BOB)
    assert r.status_code == 200
    assert [c["name"] for c in r.json()["channels"]] == ["alpha", "zebra"]


def test_list_requires_user_header(client):
    assert client.get("/channels").status_code == 401


def test_archive_channel_and_listing(client):
    cid = make(client).json()["id"]
    make(client, "random")
    r = client.post(f"/channels/{cid}/archive", headers=BOB)
    assert r.status_code == 200
    assert r.json()["archived"] is True
    assert r.json()["archived_at"] is not None

    names = [c["name"] for c in client.get("/channels", headers=ALICE).json()["channels"]]
    assert names == ["random"]

    all_ = client.get("/channels?include_archived=true", headers=ALICE).json()["channels"]
    assert sorted(c["name"] for c in all_) == ["general", "random"]


def test_archive_twice_is_409(client):
    cid = make(client).json()["id"]
    client.post(f"/channels/{cid}/archive", headers=ALICE)
    r = client.post(f"/channels/{cid}/archive", headers=ALICE)
    assert r.status_code == 409


def test_archive_unknown_channel_is_404(client):
    r = client.post("/channels/999/archive", headers=ALICE)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_archived_name_stays_reserved(client):
    cid = make(client).json()["id"]
    client.post(f"/channels/{cid}/archive", headers=ALICE)
    assert make(client).status_code == 409


def test_non_integer_channel_id_is_422(client):
    assert client.post("/channels/abc/archive", headers=ALICE).status_code == 422

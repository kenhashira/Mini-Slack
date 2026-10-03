ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}


def make_channel(client, name="general"):
    return client.post("/channels", json={"name": name}, headers=ALICE).json()["id"]


def post(client, cid, body="hi", headers=ALICE):
    return client.post(f"/channels/{cid}/messages", json={"body": body}, headers=headers)


def history(client, cid, qs="", headers=ALICE):
    return client.get(f"/channels/{cid}/messages{qs}", headers=headers)


def test_post_message(client):
    cid = make_channel(client)
    r = post(client, cid, "  hello  ")
    assert r.status_code == 201
    m = r.json()
    assert m["body"] == "hello"
    assert m["user_id"] == "alice"
    assert m["channel_id"] == cid
    assert m["parent_id"] is None
    assert m["edited_at"] is None
    assert m["reply_count"] == 0


def test_post_requires_user_header(client):
    cid = make_channel(client)
    assert client.post(f"/channels/{cid}/messages", json={"body": "x"}).status_code == 401


def test_post_to_unknown_channel_is_404(client):
    assert post(client, 999).status_code == 404


def test_post_to_archived_channel_is_409(client):
    cid = make_channel(client)
    client.post(f"/channels/{cid}/archive", headers=ALICE)
    r = post(client, cid)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_invalid_bodies_are_422(client):
    cid = make_channel(client)
    for bad in ["", "   ", "x" * 4001]:
        assert post(client, cid, bad).status_code == 422, bad
    r = client.post(f"/channels/{cid}/messages", json={}, headers=ALICE)
    assert r.status_code == 422


def test_history_is_newest_first_and_readable_when_archived(client):
    cid = make_channel(client)
    for i in range(3):
        post(client, cid, f"m{i}")
    client.post(f"/channels/{cid}/archive", headers=ALICE)
    r = history(client, cid, headers=BOB)
    assert r.status_code == 200
    assert [m["body"] for m in r.json()["messages"]] == ["m2", "m1", "m0"]
    assert r.json()["next_before"] is None


def test_history_only_shows_that_channel(client):
    a, b = make_channel(client, "a"), make_channel(client, "b")
    post(client, a, "in-a")
    post(client, b, "in-b")
    assert [m["body"] for m in history(client, a).json()["messages"]] == ["in-a"]


def test_pagination_walks_all_messages_without_overlap(client):
    cid = make_channel(client)
    for i in range(5):
        post(client, cid, f"m{i}")
    seen, before = [], None
    for _ in range(10):  # safety bound
        qs = "?limit=2" + (f"&before={before}" if before else "")
        page = history(client, cid, qs).json()
        seen += [m["body"] for m in page["messages"]]
        before = page["next_before"]
        if before is None:
            break
    assert seen == ["m4", "m3", "m2", "m1", "m0"]


def test_pagination_exact_fit_has_no_next_page(client):
    cid = make_channel(client)
    for i in range(2):
        post(client, cid, f"m{i}")
    page = history(client, cid, "?limit=2").json()
    assert len(page["messages"]) == 2
    assert page["next_before"] is None


def test_pagination_is_stable_when_new_messages_arrive(client):
    cid = make_channel(client)
    for i in range(3):
        post(client, cid, f"m{i}")
    first = history(client, cid, "?limit=2").json()
    post(client, cid, "new")
    second = history(client, cid, f"?limit=2&before={first['next_before']}").json()
    assert [m["body"] for m in second["messages"]] == ["m0"]


def test_bad_pagination_params_are_422(client):
    cid = make_channel(client)
    for qs in ["limit=0", "limit=101", "before=0", "before=abc"]:
        assert history(client, cid, f"?{qs}").status_code == 422, qs


def test_history_of_unknown_channel_is_404(client):
    assert history(client, 999).status_code == 404


def test_history_requires_user_header(client):
    cid = make_channel(client)
    assert client.get(f"/channels/{cid}/messages").status_code == 401


def test_edit_by_author(client):
    mid = post(client, make_channel(client), "old").json()["id"]
    r = client.patch(f"/messages/{mid}", json={"body": "new"}, headers=ALICE)
    assert r.status_code == 200
    assert r.json()["body"] == "new"
    assert r.json()["edited_at"] is not None


def test_edit_by_non_author_is_403_and_changes_nothing(client):
    cid = make_channel(client)
    mid = post(client, cid, "old").json()["id"]
    r = client.patch(f"/messages/{mid}", json={"body": "hack"}, headers=BOB)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert history(client, cid).json()["messages"][0]["body"] == "old"


def test_edit_error_cases(client):
    mid = post(client, make_channel(client)).json()["id"]
    assert client.patch(f"/messages/{mid}", json={"body": "x"}).status_code == 401
    assert client.patch("/messages/999", json={"body": "x"}, headers=ALICE).status_code == 404
    assert client.patch(f"/messages/{mid}", json={"body": " "}, headers=ALICE).status_code == 422


def test_delete_by_author(client):
    cid = make_channel(client)
    mid = post(client, cid).json()["id"]
    r = client.delete(f"/messages/{mid}", headers=ALICE)
    assert r.status_code == 204
    assert r.content == b""
    assert history(client, cid).json()["messages"] == []
    assert client.delete(f"/messages/{mid}", headers=ALICE).status_code == 404


def test_delete_by_non_author_is_403(client):
    cid = make_channel(client)
    mid = post(client, cid).json()["id"]
    assert client.delete(f"/messages/{mid}", headers=BOB).status_code == 403
    assert len(history(client, cid).json()["messages"]) == 1


def test_delete_without_header_is_401(client):
    mid = post(client, make_channel(client)).json()["id"]
    assert client.delete(f"/messages/{mid}").status_code == 401

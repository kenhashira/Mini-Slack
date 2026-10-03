ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}


def make_channel(client, name="general"):
    return client.post("/channels", json={"name": name}, headers=ALICE).json()["id"]


def post(client, cid, body="parent", headers=ALICE):
    return client.post(f"/channels/{cid}/messages", json={"body": body}, headers=headers).json()["id"]


def reply(client, mid, body="reply", headers=BOB):
    return client.post(f"/messages/{mid}/replies", json={"body": body}, headers=headers)


def replies(client, mid, qs="", headers=ALICE):
    return client.get(f"/messages/{mid}/replies{qs}", headers=headers)


def history(client, cid):
    return client.get(f"/channels/{cid}/messages", headers=ALICE).json()


def test_post_reply(client):
    cid = make_channel(client)
    mid = post(client, cid)
    r = reply(client, mid, "  hello  ")
    assert r.status_code == 201
    body = r.json()
    assert body["parent_id"] == mid
    assert body["channel_id"] == cid
    assert body["user_id"] == "bob"
    assert body["body"] == "hello"


def test_reply_error_cases(client):
    mid = post(client, make_channel(client))
    assert client.post(f"/messages/{mid}/replies", json={"body": "x"}).status_code == 401
    assert reply(client, 999).status_code == 404
    assert reply(client, mid, "").status_code == 422
    assert reply(client, mid, "x" * 4001).status_code == 422


def test_cannot_reply_to_a_reply(client):
    mid = post(client, make_channel(client))
    rid = reply(client, mid).json()["id"]
    r = reply(client, rid)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert replies(client, rid).status_code == 422


def test_replies_are_hidden_from_channel_history_but_counted(client):
    cid = make_channel(client)
    mid = post(client, cid)
    reply(client, mid)
    reply(client, mid)
    page = history(client, cid)
    assert [m["id"] for m in page["messages"]] == [mid]
    assert page["messages"][0]["reply_count"] == 2


def test_list_replies_oldest_first(client):
    mid = post(client, make_channel(client))
    for i in range(3):
        reply(client, mid, f"r{i}")
    r = replies(client, mid)
    assert r.status_code == 200
    assert [x["body"] for x in r.json()["replies"]] == ["r0", "r1", "r2"]
    assert r.json()["next_after"] is None


def test_list_replies_pagination(client):
    mid = post(client, make_channel(client))
    for i in range(5):
        reply(client, mid, f"r{i}")
    seen, after = [], None
    for _ in range(10):
        qs = "?limit=2" + (f"&after={after}" if after else "")
        page = replies(client, mid, qs).json()
        seen += [x["body"] for x in page["replies"]]
        after = page["next_after"]
        if after is None:
            break
    assert seen == ["r0", "r1", "r2", "r3", "r4"]


def test_list_replies_error_cases(client):
    mid = post(client, make_channel(client))
    assert client.get(f"/messages/{mid}/replies").status_code == 401
    assert replies(client, 999).status_code == 404
    for qs in ["?limit=0", "?limit=101", "?after=0"]:
        assert replies(client, mid, qs).status_code == 422, qs


def test_threads_are_separate(client):
    cid = make_channel(client)
    m1, m2 = post(client, cid, "one"), post(client, cid, "two")
    reply(client, m1, "to-one")
    assert [x["body"] for x in replies(client, m1).json()["replies"]] == ["to-one"]
    assert replies(client, m2).json()["replies"] == []


def test_reply_author_only_rules_apply(client):
    mid = post(client, make_channel(client))
    rid = reply(client, mid, "mine", BOB).json()["id"]
    assert client.patch(f"/messages/{rid}", json={"body": "x"}, headers=ALICE).status_code == 403
    assert client.delete(f"/messages/{rid}", headers=ALICE).status_code == 403
    r = client.patch(f"/messages/{rid}", json={"body": "edited"}, headers=BOB)
    assert r.status_code == 200
    assert r.json()["parent_id"] == mid
    assert client.delete(f"/messages/{rid}", headers=BOB).status_code == 204
    assert replies(client, mid).json()["replies"] == []


def test_deleting_a_reply_lowers_the_count(client):
    cid = make_channel(client)
    mid = post(client, cid)
    rid = reply(client, mid).json()["id"]
    reply(client, mid)
    client.delete(f"/messages/{rid}", headers=BOB)
    assert history(client, cid)["messages"][0]["reply_count"] == 1


def test_deleting_the_parent_deletes_its_replies(client):
    mid = post(client, make_channel(client))
    rid = reply(client, mid).json()["id"]
    assert client.delete(f"/messages/{mid}", headers=ALICE).status_code == 204
    # The reply is gone too (it cascaded), so editing it is now a 404.
    assert client.patch(f"/messages/{rid}", json={"body": "x"}, headers=BOB).status_code == 404


def test_archived_channel_is_read_only_for_threads(client):
    cid = make_channel(client)
    mid = post(client, cid)
    rid = reply(client, mid).json()["id"]
    client.post(f"/channels/{cid}/archive", headers=ALICE)

    r = reply(client, mid)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert client.patch(f"/messages/{rid}", json={"body": "x"}, headers=BOB).status_code == 409
    assert client.delete(f"/messages/{rid}", headers=BOB).status_code == 409
    # ...but reading still works and nothing changed.
    assert [x["id"] for x in replies(client, mid).json()["replies"]] == [rid]

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
CAROL = {"X-User-Id": "carol"}


def make_channel(client, name="general"):
    return client.post("/channels", json={"name": name}, headers=ALICE).json()["id"]


def post(client, cid, body="hi", headers=ALICE):
    return client.post(f"/channels/{cid}/messages", json={"body": body}, headers=headers).json()["id"]


def reply(client, mid, headers=BOB):
    return client.post(f"/messages/{mid}/replies", json={"body": "r"}, headers=headers).json()["id"]


def mark_read(client, cid, message_id=None, headers=BOB):
    if message_id is None:
        return client.post(f"/channels/{cid}/read", headers=headers)
    return client.post(f"/channels/{cid}/read", json={"message_id": message_id}, headers=headers)


def unread(client, headers=BOB, name="general"):
    channels = client.get("/channels?include_archived=true", headers=headers).json()["channels"]
    return next(c for c in channels if c["name"] == name)["unread_count"]


def marker(conn, user="bob", cid=1):
    row = conn.execute(
        "SELECT last_read_message_id FROM read_markers WHERE user_id = ? AND channel_id = ?",
        (user, cid),
    ).fetchone()
    return row[0] if row else None


def test_never_opened_channel_counts_all_messages_from_others(client):
    cid = make_channel(client)
    for _ in range(3):
        post(client, cid)
    assert unread(client, BOB) == 3


def test_empty_channel_has_zero_unread(client):
    make_channel(client)
    assert unread(client, BOB) == 0


def test_own_messages_are_not_unread(client):
    cid = make_channel(client)
    post(client, cid, headers=ALICE)
    post(client, cid, headers=ALICE)
    post(client, cid, headers=BOB)
    assert unread(client, ALICE) == 1  # only bob's message
    assert unread(client, BOB) == 2  # only alice's two


def test_replies_are_not_counted(client):
    cid = make_channel(client)
    mid = post(client, cid)
    reply(client, mid, CAROL)
    reply(client, mid, CAROL)
    assert unread(client, BOB) == 1  # just the top-level message


def test_mark_read_defaults_to_newest_top_level_message(client, conn):
    cid = make_channel(client)
    post(client, cid)
    newest = post(client, cid)
    reply(client, newest)  # a later reply must not become the marker
    r = mark_read(client, cid)
    assert r.status_code == 200
    assert r.json() == {"channel_id": cid, "last_read_message_id": newest, "unread_count": 0}
    assert unread(client, BOB) == 0


def test_mark_read_up_to_a_specific_message(client):
    cid = make_channel(client)
    m1, m2, m3 = post(client, cid), post(client, cid), post(client, cid)
    r = mark_read(client, cid, m2)
    assert r.json() == {"channel_id": cid, "last_read_message_id": m2, "unread_count": 1}
    assert unread(client, BOB) == 1  # m3 only


def test_new_messages_after_marking_read_are_unread(client):
    cid = make_channel(client)
    post(client, cid)
    mark_read(client, cid)
    post(client, cid)
    post(client, cid)
    assert unread(client, BOB) == 2


def test_marker_never_moves_backward(client, conn):
    cid = make_channel(client)
    m1, m2, m3 = post(client, cid), post(client, cid), post(client, cid)
    mark_read(client, cid, m3)
    r = mark_read(client, cid, m1)
    assert r.status_code == 200
    assert r.json()["last_read_message_id"] == m3
    assert marker(conn) == m3
    assert unread(client, BOB) == 0


def test_marking_read_on_an_empty_channel_is_a_noop(client):
    cid = make_channel(client)
    r = mark_read(client, cid)
    assert r.status_code == 200
    assert r.json()["last_read_message_id"] == 0
    assert r.json()["unread_count"] == 0


def test_deleting_the_marked_message_does_not_reset_the_marker(client, conn):
    cid = make_channel(client)
    m1, m2, m3 = post(client, cid), post(client, cid), post(client, cid)
    mark_read(client, cid, m2)
    assert client.delete(f"/messages/{m2}", headers=ALICE).status_code == 204
    assert marker(conn) == m2  # still stored
    assert unread(client, BOB) == 1  # m3 is still the only unread message


def test_deleting_the_newest_marked_message_does_not_make_later_ones_read(client, conn):
    cid = make_channel(client)
    post(client, cid)
    m2 = post(client, cid)
    mark_read(client, cid)  # marker = m2
    client.delete(f"/messages/{m2}", headers=ALICE)
    assert marker(conn) == m2
    post(client, cid)  # ids are never reused, so this id is above the marker
    assert unread(client, BOB) == 1


def test_mark_read_unknown_message_is_404(client):
    cid = make_channel(client)
    r = mark_read(client, cid, 999)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_mark_read_message_from_another_channel_is_422(client, conn):
    a, b = make_channel(client, "a"), make_channel(client, "b")
    other = post(client, b)
    r = mark_read(client, a, other)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert marker(conn, cid=a) is None


def test_mark_read_a_reply_is_422(client):
    cid = make_channel(client)
    rid = reply(client, post(client, cid))
    assert mark_read(client, cid, rid).status_code == 422


def test_mark_read_error_cases(client):
    cid = make_channel(client)
    assert client.post(f"/channels/{cid}/read").status_code == 401
    assert mark_read(client, 999).status_code == 404
    for bad in [0, -1]:
        assert mark_read(client, cid, bad).status_code == 422, bad
    r = client.post(f"/channels/{cid}/read", json={"message_id": "abc"}, headers=BOB)
    assert r.status_code == 422


def test_mark_read_works_in_archived_channel(client):
    cid = make_channel(client)
    post(client, cid)
    client.post(f"/channels/{cid}/archive", headers=ALICE)
    r = mark_read(client, cid)
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0
    assert unread(client, BOB) == 0


def test_markers_are_per_user_and_per_channel(client):
    a, b = make_channel(client, "a"), make_channel(client, "b")
    post(client, a)
    post(client, b)
    mark_read(client, a, headers=BOB)
    assert unread(client, BOB, "a") == 0
    assert unread(client, BOB, "b") == 1  # other channel untouched
    assert unread(client, CAROL, "a") == 1  # other user untouched


def test_channel_list_shows_unread_count_per_channel(client):
    a, b = make_channel(client, "a"), make_channel(client, "b")
    for _ in range(2):
        post(client, a)
    post(client, b)
    channels = client.get("/channels", headers=BOB).json()["channels"]
    assert {c["name"]: c["unread_count"] for c in channels} == {"a": 2, "b": 1}


def test_deleted_unread_messages_stop_counting(client):
    cid = make_channel(client)
    mid = post(client, cid)
    post(client, cid)
    client.delete(f"/messages/{mid}", headers=ALICE)
    assert unread(client, BOB) == 1

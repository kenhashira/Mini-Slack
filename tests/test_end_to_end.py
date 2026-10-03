"""Scenario tests: several features working together, the way a client would use them."""
ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
CAROL = {"X-User-Id": "carol"}


def make_channel(client, name="general"):
    return client.post("/channels", json={"name": name}, headers=ALICE).json()["id"]


def post(client, cid, body="hi", headers=ALICE):
    return client.post(f"/channels/{cid}/messages", json={"body": body}, headers=headers).json()["id"]


def unread(client, headers, name="general"):
    channels = client.get("/channels", headers=headers).json()["channels"]
    return next(c for c in channels if c["name"] == name)["unread_count"]


def test_unread_lifecycle_including_deleting_the_marked_message(client, conn):
    cid = make_channel(client)

    # A posts; B's unread count rises with each message.
    assert unread(client, BOB) == 0
    post(client, cid, "first")
    assert unread(client, BOB) == 1
    m2 = post(client, cid, "second")
    assert unread(client, BOB) == 2

    # B marks read: count drops to 0.
    r = client.post(f"/channels/{cid}/read", headers=BOB)
    assert r.json()["last_read_message_id"] == m2
    assert unread(client, BOB) == 0

    # A deletes the message B's marker points at: count stays 0 and the marker is kept.
    assert client.delete(f"/messages/{m2}", headers=ALICE).status_code == 204
    assert unread(client, BOB) == 0
    stored = conn.execute(
        "SELECT last_read_message_id FROM read_markers WHERE user_id = 'bob'"
    ).fetchone()[0]
    assert stored == m2

    # A new message lands above the marker, so it is the only unread one.
    post(client, cid, "third")
    assert unread(client, BOB) == 1

    # Alice wrote everything, so none of it is unread for her.
    assert unread(client, ALICE) == 0


def test_full_conversation_flow(client):
    cid = make_channel(client, "launch")
    question = post(client, cid, "Ship on Friday?", ALICE)

    # Bob replies in a thread; Carol reacts to the question and to Bob's reply.
    reply = client.post(f"/messages/{question}/replies", json={"body": "Yes!"}, headers=BOB).json()
    r = client.post(f"/messages/{question}/reactions", json={"emoji": "👍"}, headers=CAROL)
    assert r.status_code == 201
    r = client.post(f"/messages/{reply['id']}/reactions", json={"emoji": "🎉"}, headers=CAROL)
    assert r.status_code == 201

    # The feed shows one top-level message with its thread count and reaction.
    feed = client.get(f"/channels/{cid}/messages", headers=CAROL).json()["messages"]
    assert [m["id"] for m in feed] == [question]
    assert feed[0]["reply_count"] == 1
    assert feed[0]["reactions"] == [{"emoji": "👍", "count": 1, "reacted": True}]

    # Bob has not read the channel: Alice's question is unread for him (his reply is not counted).
    assert unread(client, BOB, "launch") == 1

    # Bob can't edit Alice's question, but Alice can; reactions survive the edit.
    assert client.patch(f"/messages/{question}", json={"body": "x"}, headers=BOB).status_code == 403
    edited = client.patch(
        f"/messages/{question}", json={"body": "Ship on Monday?"}, headers=ALICE
    ).json()
    assert edited["edited_at"] is not None
    assert edited["reactions"] == [{"emoji": "👍", "count": 1, "reacted": False}]

    # Archiving freezes every content change, but reading and marking read still work.
    assert client.post(f"/channels/{cid}/archive", headers=ALICE).status_code == 200
    writes = [
        client.post(f"/channels/{cid}/messages", json={"body": "x"}, headers=ALICE),
        client.patch(f"/messages/{question}", json={"body": "x"}, headers=ALICE),
        client.delete(f"/messages/{question}", headers=ALICE),
        client.post(f"/messages/{question}/replies", json={"body": "x"}, headers=BOB),
        client.post(f"/messages/{question}/reactions", json={"emoji": "🔥"}, headers=BOB),
        client.delete(f"/messages/{question}/reactions", params={"emoji": "👍"}, headers=CAROL),
    ]
    assert [w.status_code for w in writes] == [409] * 6
    assert client.get(f"/messages/{question}/replies", headers=BOB).status_code == 200
    assert client.post(f"/channels/{cid}/read", headers=BOB).status_code == 200

    # Every blocked write left the content untouched.
    feed = client.get(f"/channels/{cid}/messages", headers=BOB).json()["messages"]
    assert [m["body"] for m in feed] == ["Ship on Monday?"]
    assert feed[0]["reactions"] == [{"emoji": "👍", "count": 1, "reacted": False}]

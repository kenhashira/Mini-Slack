ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
CAROL = {"X-User-Id": "carol"}


def make_channel(client, name="general"):
    return client.post("/channels", json={"name": name}, headers=ALICE).json()["id"]


def post(client, cid, body="hello"):
    return client.post(f"/channels/{cid}/messages", json={"body": body}, headers=ALICE).json()["id"]


def react(client, mid, emoji="👍", headers=BOB):
    return client.post(f"/messages/{mid}/reactions", json={"emoji": emoji}, headers=headers)


def unreact(client, mid, emoji="👍", headers=BOB):
    return client.delete(f"/messages/{mid}/reactions", params={"emoji": emoji}, headers=headers)


def history(client, cid, headers=ALICE):
    return client.get(f"/channels/{cid}/messages", headers=headers).json()["messages"]


def test_add_reaction_returns_message_with_reactions(client):
    mid = post(client, make_channel(client))
    r = react(client, mid)
    assert r.status_code == 201
    assert r.json()["id"] == mid
    assert r.json()["reactions"] == [{"emoji": "👍", "count": 1, "reacted": True}]


def test_new_messages_have_no_reactions(client):
    cid = make_channel(client)
    post(client, cid)
    assert history(client, cid)[0]["reactions"] == []


def test_emoji_is_trimmed(client):
    mid = post(client, make_channel(client))
    assert react(client, mid, "  :tada:  ").json()["reactions"][0]["emoji"] == ":tada:"


def test_invalid_emoji_is_422(client):
    mid = post(client, make_channel(client))
    for bad in ["", "   ", "x" * 65]:
        assert react(client, mid, bad).status_code == 422, bad
    assert client.post(f"/messages/{mid}/reactions", json={}, headers=BOB).status_code == 422
    assert unreact(client, mid, "   ").status_code == 422
    assert client.delete(f"/messages/{mid}/reactions", headers=BOB).status_code == 422


def test_emoji_of_64_characters_is_allowed(client):
    mid = post(client, make_channel(client))
    assert react(client, mid, "x" * 64).status_code == 201


def test_duplicate_reaction_is_409(client):
    mid = post(client, make_channel(client))
    assert react(client, mid).status_code == 201
    r = react(client, mid)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    # Trimming means " 👍 " is the same emoji.
    assert react(client, mid, " 👍 ").status_code == 409


def test_same_user_can_use_different_emoji_and_different_users_can_share_one(client):
    mid = post(client, make_channel(client))
    assert react(client, mid, "👍", BOB).status_code == 201
    assert react(client, mid, "🎉", BOB).status_code == 201
    assert react(client, mid, "👍", CAROL).status_code == 201


def test_reactions_are_grouped_with_counts_and_caller_flag(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍", BOB)
    react(client, mid, "👍", CAROL)
    react(client, mid, "🎉", CAROL)

    as_bob = history(client, cid, BOB)[0]["reactions"]
    assert as_bob == [
        {"emoji": "👍", "count": 2, "reacted": True},
        {"emoji": "🎉", "count": 1, "reacted": False},
    ]
    as_alice = history(client, cid, ALICE)[0]["reactions"]
    assert as_alice == [
        {"emoji": "👍", "count": 2, "reacted": False},
        {"emoji": "🎉", "count": 1, "reacted": False},
    ]


def test_reactions_show_on_the_right_message_only(client):
    cid = make_channel(client)
    m1, m2 = post(client, cid, "one"), post(client, cid, "two")
    react(client, m1)
    by_id = {m["id"]: m for m in history(client, cid)}
    assert by_id[m1]["reactions"] != []
    assert by_id[m2]["reactions"] == []


def test_reactions_show_on_replies_and_in_thread_listing(client):
    mid = post(client, make_channel(client))
    rid = client.post(f"/messages/{mid}/replies", json={"body": "r"}, headers=BOB).json()["id"]
    assert react(client, rid, "👍", CAROL).status_code == 201
    listed = client.get(f"/messages/{mid}/replies", headers=CAROL).json()["replies"]
    assert listed[0]["reactions"] == [{"emoji": "👍", "count": 1, "reacted": True}]


def test_editing_a_message_keeps_its_reactions_in_the_response(client):
    mid = post(client, make_channel(client))
    react(client, mid, "👍", ALICE)
    r = client.patch(f"/messages/{mid}", json={"body": "edited"}, headers=ALICE)
    assert r.json()["reactions"] == [{"emoji": "👍", "count": 1, "reacted": True}]


def test_remove_own_reaction(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid)
    r = unreact(client, mid)
    assert r.status_code == 204
    assert r.content == b""
    assert history(client, cid)[0]["reactions"] == []


def test_remove_reaction_that_does_not_exist_is_404(client):
    mid = post(client, make_channel(client))
    assert unreact(client, mid).status_code == 404
    react(client, mid, "🎉")
    assert unreact(client, mid, "👍").status_code == 404  # different emoji


def test_cannot_remove_someone_elses_reaction(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍", BOB)
    r = unreact(client, mid, "👍", CAROL)
    assert r.status_code == 404
    assert history(client, cid)[0]["reactions"] == [{"emoji": "👍", "count": 1, "reacted": False}]


def test_removing_my_reaction_leaves_others(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍", BOB)
    react(client, mid, "👍", CAROL)
    unreact(client, mid, "👍", BOB)
    assert history(client, cid, CAROL)[0]["reactions"] == [
        {"emoji": "👍", "count": 1, "reacted": True}
    ]


def test_can_react_again_after_removing(client):
    mid = post(client, make_channel(client))
    react(client, mid)
    unreact(client, mid)
    assert react(client, mid).status_code == 201


def test_missing_header_and_unknown_message(client):
    mid = post(client, make_channel(client))
    assert client.post(f"/messages/{mid}/reactions", json={"emoji": "👍"}).status_code == 401
    assert client.delete(f"/messages/{mid}/reactions", params={"emoji": "👍"}).status_code == 401
    assert react(client, 999).status_code == 404
    assert unreact(client, 999).status_code == 404


def test_archived_channel_is_read_only_for_reactions(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍", BOB)
    client.post(f"/channels/{cid}/archive", headers=ALICE)

    r = react(client, mid, "🎉", CAROL)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert unreact(client, mid, "👍", BOB).status_code == 409
    # Reading still works and nothing changed.
    assert history(client, cid)[0]["reactions"] == [{"emoji": "👍", "count": 1, "reacted": False}]


def test_deleting_a_message_deletes_its_reactions(client, conn):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍", BOB)
    react(client, mid, "🎉", CAROL)
    assert conn.execute("SELECT COUNT(*) FROM reactions").fetchone()[0] == 2
    assert client.delete(f"/messages/{mid}", headers=ALICE).status_code == 204
    assert conn.execute("SELECT COUNT(*) FROM reactions").fetchone()[0] == 0


def test_remove_applies_the_same_emoji_rules_as_add(client):
    mid = post(client, make_channel(client))
    react(client, mid, "👍")
    assert unreact(client, mid, "x" * 65).status_code == 422
    assert unreact(client, mid, "  👍  ").status_code == 204  # trimmed, so it matches


def raw_delete(client, mid, encoded_emoji, headers=BOB):
    """DELETE with a hand-encoded query string, the way curl or a browser would send it."""
    return client.delete(f"/messages/{mid}/reactions?emoji={encoded_emoji}", headers=headers)


def test_remove_a_real_emoji_with_url_encoding(client):
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, "👍")
    assert raw_delete(client, mid, "%F0%9F%91%8D").status_code == 204  # thumbs-up as UTF-8 percent-encoding
    assert history(client, cid)[0]["reactions"] == []


def test_remove_multi_codepoint_emoji_with_url_encoding(client):
    from urllib.parse import quote

    cid = make_channel(client)
    mid = post(client, cid)
    # A skin-tone modifier and a ZWJ family sequence are several code points each.
    for emoji in ["👍🏽", "👨‍👩‍👧"]:
        react(client, mid, emoji)
        assert raw_delete(client, mid, quote(emoji)).status_code == 204, emoji
    assert history(client, cid)[0]["reactions"] == []


def test_plus_in_shortcode_must_be_encoded_as_percent_2b(client):
    # In a query string a bare '+' means a space, so ":+1:" has to be sent as ":%2B1:".
    cid = make_channel(client)
    mid = post(client, cid)
    react(client, mid, ":+1:")
    assert raw_delete(client, mid, ":+1:").status_code == 404  # bare + was read as a space
    assert raw_delete(client, mid, ":%2B1:").status_code == 204
    assert history(client, cid)[0]["reactions"] == []

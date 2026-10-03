# Mini-Slack

A small Slack-style messaging API built with **FastAPI** and **SQLite** (plain `sqlite3`, no ORM).

- Channels: create, list, archive (archived channels are read-only)
- Messages: post, edit, delete (author only), newest-first paginated history
- Threaded replies (one level deep)
- Emoji reactions (one per user per emoji)
- Unread counts using a per-user read marker
- One consistent JSON error format (401 / 403 / 404 / 409 / 422)

> This is a portfolio project. It has **no real authentication**; read [Limitations](#limitations) before using it for anything else.

## Run it locally

You need Python 3.12 or newer. (CI tests on 3.12.)

### Windows (PowerShell)

No virtual environment activation is needed; calling `python -m` keeps everything pointed at the same Python.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API is now at <http://localhost:8000>. FastAPI's interactive docs are at <http://localhost:8000/docs>.

The database is a SQLite file, `mini_slack.db`, created in the current folder on first start. Set the `MINI_SLACK_DB` environment variable to use a different path.

### Run the tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Each test uses its own temporary database. For a coverage report (optional): `python -m pytest --cov=app --cov-report=term-missing`.

## Run it with Docker

```bash
docker build -t mini-slack .
docker run -d --name mini-slack -p 8000:8000 -v minislack:/data mini-slack
```

- The container runs as a non-root user and stores its database at `/data/mini_slack.db`. The named volume `minislack` keeps your data when the container is removed or replaced.
- If you use a bind mount instead of a named volume (for example `-v "$(pwd)/data:/data"`), the host folder's permissions apply, and the container user (uid 10001) must be able to write to it.
- **Verification:** the image is built, started and checked by the GitHub Actions `docker` job on every push (see [.github/workflows/ci.yml](.github/workflows/ci.yml)). That job waits for `GET /health` to return 200, checks the container is not running as root, creates a channel to prove the database can be written to `/data`, and confirms the data survives a container restart.

## Identifying the caller: `X-User-Id`

There are no accounts and no passwords. Every endpoint except `/health` and FastAPI's built-in documentation pages (`/docs`, `/redoc`, `/openapi.json`) needs an `X-User-Id` header naming the caller, for example `X-User-Id: alice`.

- A **missing or blank** header returns **401**.
- The header is **trusted as-is**. Users are created automatically the first time they are seen. Anyone can send any user id.
- **403** is a different thing: you are identified, but you are not allowed to do that (editing or deleting someone else's message).

## Endpoints

All bodies and responses are JSON. `{id}` values are integers. Timestamps are UTC, formatted `YYYY-MM-DD HH:MM:SS`.

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| GET | `/health` | Liveness check (no header needed) | 200 |
| GET | `/me` | Echo the caller's user id | 200 |
| POST | `/channels` | Create a channel. Body: `{"name": "general"}` | 201 |
| GET | `/channels` | List channels with `unread_count` for the caller. Query: `include_archived=true` to include archived ones | 200 |
| POST | `/channels/{id}/archive` | Archive a channel (it becomes read-only) | 200 |
| POST | `/channels/{id}/messages` | Post a message. Body: `{"body": "hello"}` | 201 |
| GET | `/channels/{id}/messages` | Message history, newest first, top-level messages only. Query: `limit`, `before` | 200 |
| PATCH | `/messages/{id}` | Edit a message (author only). Body: `{"body": "new text"}` | 200 |
| DELETE | `/messages/{id}` | Delete a message and its replies and reactions (author only) | 204 |
| POST | `/messages/{id}/replies` | Reply in a thread. Body: `{"body": "..."}` | 201 |
| GET | `/messages/{id}/replies` | List a thread, oldest first. Query: `limit`, `after` | 200 |
| POST | `/messages/{id}/reactions` | Add a reaction. Body: `{"emoji": "👍"}` | 201 |
| DELETE | `/messages/{id}/reactions?emoji=...` | Remove **your own** reaction | 204 |
| POST | `/channels/{id}/read` | Mark read. Optional body: `{"message_id": 12}` | 200 |

### Limits and validation

- Channel name: 1-80 characters, letters, digits, `-` and `_`, starting with a letter or digit. Unique ignoring case (`General` and `general` clash, and an archived channel keeps its name).
- Message and reply body: 1-4000 characters after trimming.
- Emoji: any text, 1-64 characters after trimming (`👍` or `:tada:` both work).
- `limit`: 1-100, default 50.

### Messages and reactions in responses

Every message looks like this:

```json
{
  "id": 3,
  "channel_id": 1,
  "user_id": "alice",
  "parent_id": null,
  "body": "Ship on Friday?",
  "created_at": "2026-10-03 14:40:06",
  "edited_at": null,
  "reply_count": 1,
  "reactions": [{ "emoji": "👍", "count": 2, "reacted": true }]
}
```

`reactions` groups by emoji. `count` is how many users used it, and `reacted` says whether **the caller** is one of them. `parent_id` is set only on replies.

### Pagination

Both lists use cursors rather than page numbers, so new messages arriving mid-scroll cannot cause skipped or repeated items.

- **Channel history** (`GET /channels/{id}/messages`): newest first. Response: `{"messages": [...], "next_before": 41}`. To get the next page, send `before=41`. `next_before` is `null` on the last page.
- **Thread replies** (`GET /messages/{id}/replies`): oldest first. Response: `{"replies": [...], "next_after": 57}`. To get the next page, send `after=57`. `next_after` is `null` on the last page.

```
GET /channels/1/messages?limit=20
GET /channels/1/messages?limit=20&before=41
GET /messages/3/replies?limit=20&after=57
```

### Threads

A reply is a message with a `parent_id`. Threads are one level deep: replying to a reply returns 422. Replies do not appear in channel history; each top-level message shows a `reply_count`. Replies can be edited, deleted and reacted to like any other message. Deleting a message deletes its replies.

### Reactions

- A user can add each emoji to a message once. Repeating it returns 409.
- Removing takes the emoji in the query string, and only ever removes **your own** reaction. If you do not have that reaction (including when it belongs to someone else), the response is 404.
- **URL-encode the emoji.** In a query string a bare `+` means a space, so `:+1:` must be sent as `:%2B1:`. A real emoji should be percent-encoded as UTF-8, for example `👍` is `%F0%9F%91%8D`. Most HTTP libraries do this for you.

### Unread counts

Each user has a read marker per channel. `unread_count` in `GET /channels` is the number of **top-level** messages in that channel that are **not yours** and are **newer than your marker**. Replies are not counted. A channel you have never opened counts every top-level message from other people.

`POST /channels/{id}/read` moves your marker forward:

- With no body it marks everything up to the newest top-level message as read. With `{"message_id": 12}` it marks up to that message.
- The marker **only moves forward**. Marking an older message read leaves it where it was.
- The message must exist (404 otherwise), be in that channel and be a top-level message (422 otherwise).
- Deleting the message your marker points at does **not** reset the marker.
- It works in archived channels, because it does not change any content.
- Response: `{"channel_id": 1, "last_read_message_id": 12, "unread_count": 0}`.

### Archived channels

An archived channel is **read-only**: posting, editing, deleting, replying and reacting all return **409**. Reading history and threads, and marking read, still work.

### Errors

Every error has the same shape:

```json
{ "error": { "code": "not_found", "message": "Channel 999 not found." } }
```

| Status | `code` | When |
| --- | --- | --- |
| 401 | `unauthorized` | `X-User-Id` header missing or blank |
| 403 | `forbidden` | Identified, but not allowed (not the message's author) |
| 404 | `not_found` | Channel, message or reaction does not exist (also unknown routes) |
| 409 | `conflict` | Duplicate channel name, already archived, channel is archived and read-only, duplicate reaction |
| 422 | `validation_error` | Invalid input, including replying to a reply. Includes a `details` list of `{"field", "message"}` |
| 405 | `http_error` | Wrong HTTP method for a route |

Checks run in this order: 401 (who are you), then 404 (does it exist), then 403 (is it yours, for edit and delete), then 409 (is the channel archived). For example, someone who edits another user's message in an archived channel gets 403, not 409.

## Examples

The examples assume the server is running on `localhost:8000`.

### curl on macOS / Linux (bash)

```bash
curl -s -X POST localhost:8000/channels \
  -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"name":"general"}'

curl -s -X POST localhost:8000/channels/1/messages \
  -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"body":"Hello, team!"}'

curl -s -X POST localhost:8000/messages/1/replies \
  -H "X-User-Id: bob" -H "Content-Type: application/json" \
  -d '{"body":"Welcome!"}'

# React with a thumbs-up. The emoji is written as a JSON escape (a surrogate pair)
# so the command is plain ASCII and cannot be mangled by the terminal's encoding.
curl -s -X POST localhost:8000/messages/1/reactions \
  -H "X-User-Id: bob" -H "Content-Type: application/json" \
  -d '{"emoji":"\ud83d\udc4d"}'

# Remove it again: the emoji is percent-encoded in the query string.
curl -s -X DELETE "localhost:8000/messages/1/reactions?emoji=%F0%9F%91%8D" -H "X-User-Id: bob"

# Bob's unread counts, then mark the channel read.
curl -s localhost:8000/channels -H "X-User-Id: bob"
curl -s -X POST localhost:8000/channels/1/read -H "X-User-Id: bob"

# History, then the next page.
curl -s "localhost:8000/channels/1/messages?limit=1" -H "X-User-Id: bob"
curl -s "localhost:8000/channels/1/messages?limit=1&before=1" -H "X-User-Id: bob"
```

### curl in Windows PowerShell

Windows PowerShell 5.1 mangles quotes, and even splits arguments at spaces, when it passes inline JSON to `curl.exe` (`-d '{"body":"Hello, team!"}'` arrives as `{"body":"Hello,` and fails with a 422). The reliable way is to **pipe the JSON in** and have curl read it from stdin with `-d "@-"`. These examples were run in Windows PowerShell 5.1.

```powershell
# Send a JSON body: single-quote the JSON, pipe it, and use -d "@-"
'{"name":"general"}' | curl.exe -s -X POST localhost:8000/channels `
  -H "X-User-Id: alice" -H "Content-Type: application/json" -d "@-"

'{"body":"Hello, team!"}' | curl.exe -s -X POST localhost:8000/channels/1/messages `
  -H "X-User-Id: alice" -H "Content-Type: application/json" -d "@-"

'{"body":"Welcome!"}' | curl.exe -s -X POST localhost:8000/messages/1/replies `
  -H "X-User-Id: bob" -H "Content-Type: application/json" -d "@-"

# GET and bodyless POSTs need no special quoting
curl.exe -s localhost:8000/channels -H "X-User-Id: bob"
curl.exe -s -X POST localhost:8000/channels/1/read -H "X-User-Id: bob"

# Reactions: write the emoji as a JSON escape (Windows curl.exe corrupts raw emoji in
# command-line text), and percent-encode it in the URL when removing
'{"emoji":"\ud83d\udc4d"}' | curl.exe -s -X POST localhost:8000/messages/1/reactions `
  -H "X-User-Id: bob" -H "Content-Type: application/json" -d "@-"
curl.exe -s -X DELETE "localhost:8000/messages/1/reactions?emoji=%F0%9F%91%8D" -H "X-User-Id: bob"
```

Use `curl.exe`, not `curl`: in Windows PowerShell 5.1, plain `curl` is an alias for `Invoke-WebRequest`.

Or skip curl and use PowerShell's own cmdlet, which handles the JSON for you:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/channels `
  -Headers @{ "X-User-Id" = "alice" } -ContentType "application/json" `
  -Body (@{ name = "random" } | ConvertTo-Json)
```

## Project layout

```
app/
  main.py          app factory, wires the routers together
  db.py            SQLite schema, connections, per-request connection
  deps.py          X-User-Id handling
  errors.py        the single error format
  schemas.py       request validation
  routers/         channels.py, messages.py (incl. threads), reactions.py
tests/             one test file per feature, plus end-to-end and error-contract tests
scripts/           wait-for-health.sh (used by CI)
Dockerfile
.github/workflows/ci.yml
```

## Limitations

- **No real authentication.** The `X-User-Id` header is trusted as-is, so anyone can act as any user: edit "their own" messages, mark their read markers, and so on. The author-only rules only protect users from each other if the header is honest. A real deployment would put a proper login (sessions or tokens) in front of this.
- **Any user can archive any channel.** There are no roles or channel ownership rules, and there is no way to un-archive.
- **SQLite, single node.** One database file and one process. There is no replication, and heavy concurrent writes will queue behind SQLite's single-writer lock. It is not meant to scale horizontally.
- **Hard delete.** Deleting a message removes it for good, along with its replies and reactions. There is no soft delete, trash or edit history.
- **No rate limiting.** Nothing stops a client from sending requests as fast as it likes.
- **No thread-level unread counts.** Unread counts are per channel and count top-level messages only. New replies do not raise any count, and there is no per-thread read marker.
- Also worth knowing: there is no user list or profile endpoint, no search, no real-time push (clients must poll), and channel membership does not exist (every user can see and post in every channel).

## License

MIT. See [LICENSE](LICENSE).

# bot/__main__.py
import os
import signal
import sys
import time

import psycopg
import requests

DB_URL = os.environ.get("DATABASE_URL")
TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not DB_URL:
    print("ERROR: DATABASE_URL not set", flush=True)
    sys.exit(1)
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set", flush=True)
    sys.exit(1)

API = f"https://api.telegram.org/bot{TOKEN}"
stop = False


def _sigterm(_s, _f):
    global stop
    stop = True


signal.signal(signal.SIGINT, _sigterm)
signal.signal(signal.SIGTERM, _sigterm)


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_heartbeats(
                id bigserial primary key,
                ts timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists bot_state(
                key text primary key,
                value text not null
            )
            """
        )
    conn.commit()


def get_offset(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("select value from bot_state where key='tg_offset'")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def save_offset(conn: psycopg.Connection, next_offset: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_state(key, value)
            values('tg_offset', %s)
            on conflict (key) do update set value = excluded.value
            """,
            (str(next_offset),),
        )
    conn.commit()


def heartbeat(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into bot_heartbeats default values")
    conn.commit()


def send(chat_id: int, text: str) -> None:
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"send error: {e}", flush=True)


def handle_message(chat_id: int, text: str) -> None:
    t = (text or "").strip()
    if not t:
        return
    lower = t.lower()
    if lower in ("/start", "start"):
        send(chat_id, "🦁 Welcome! Send /ping to test.\nUse /help for commands.")
        return
    if lower in ("/help", "help"):
        send(chat_id, "Commands:\n/start – welcome\n/ping – health check")
        return
    if lower in ("/ping", "ping"):
        send(chat_id, "🦁 pong")
        return


def poll_updates(conn: psycopg.Connection) -> None:
    offset = get_offset(conn)
    params = {"timeout": 25}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{API}/getUpdates", params=params, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"getUpdates error: {e}", flush=True)
        time.sleep(5)
        return

    if not data.get("ok"):
        print(f"getUpdates not ok: {data}", flush=True)
        time.sleep(10)
        return

    updates = data.get("result", [])
    if not updates:
        return

    max_update_id = 0
    for upd in updates:
        max_update_id = max(max_update_id, upd.get("update_id", 0))
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = msg.get("text") or ""
        if chat_id is None:
            continue
        handle_message(chat_id, text)

    if max_update_id:
        save_offset(conn, max_update_id + 1)


def main() -> None:
    print("Connecting...", flush=True)
    with psycopg.connect(DB_URL, autocommit=False) as conn:
        ensure_schema(conn)
        print("Connected. Entering loop.", flush=True)
        last_hb = 0.0
        while not stop:
            now = time.time()
            if now - last_hb >= 60:
                try:
                    heartbeat(conn)
                    print("✓ heartbeat", flush=True)
                except Exception as e:
                    print(f"DB error: {e}", flush=True)
                    time.sleep(5)
                last_hb = now
            poll_updates(conn)
    print("Shutdown clean.", flush=True)


if __name__ == "__main__":
    main()

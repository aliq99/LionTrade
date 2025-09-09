# bot/__main__.py
import os
import signal
import sys
import time
from typing import Optional

import psycopg
import requests

DB_URL = os.environ.get("DATABASE_URL")
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ORG_ID = os.environ.get("ORG_ID")  # <-- set per-tenant; optional but recommended
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else None

stop = False


def _sigterm(_s, _f):
    global stop
    stop = True


def ensure_schema(conn: psycopg.Connection):
    with conn.cursor() as cur:
        # base table (your existing table may already exist)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_heartbeats (
              id BIGSERIAL PRIMARY KEY,
              ts timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        # add multitenancy columns if missing
        cur.execute("ALTER TABLE bot_heartbeats ADD COLUMN IF NOT EXISTS org_id uuid;")
        cur.execute("ALTER TABLE bot_heartbeats ADD COLUMN IF NOT EXISTS bot_id uuid;")
    conn.commit()


def heartbeat(conn: psycopg.Connection, org_id: Optional[str]):
    with conn.cursor() as cur:
        if org_id:
            cur.execute(
                "INSERT INTO bot_heartbeats (org_id) VALUES (%s);",
                (org_id,),
            )
        else:
            cur.execute("INSERT INTO bot_heartbeats DEFAULT VALUES;")
    conn.commit()


def tg_send(chat_id: int, text: str):
    if not API:
        return
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception as e:
        print(f"sendMessage error: {e}", flush=True)


def tg_poll_loop():
    if not API:
        return
    offset = None
    while not stop:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={
                    "timeout": 25,
                    "offset": offset,
                    "allowed_updates": ["message"],
                },
                timeout=30,
            )
            data = r.json()
            if not data.get("ok"):
                print(f"getUpdates not ok: {data}", flush=True)
                time.sleep(5)
                continue

            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                txt = (msg.get("text") or "").strip().lower()

                if not chat_id:
                    continue

                if txt in ("/start", "start", "hi", "hello"):
                    tg_send(chat_id, "🦁 online")
                elif txt.startswith("/ping") or txt == "ping":
                    tg_send(chat_id, "🦁 pong")
        except Exception as e:
            print(f"poll error: {e}", flush=True)
            time.sleep(5)


def main():
    if not DB_URL:
        print("ERROR: DATABASE_URL not set", flush=True)
        sys.exit(1)
    if not TOKEN:
        print("ERROR: TELEGRAM_TOKEN not set", flush=True)
        sys.exit(1)

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    print("Connecting...", flush=True)
    with psycopg.connect(DB_URL, autocommit=False) as conn:
        ensure_schema(conn)
        print("Connected. Entering loop.", flush=True)

        # simple cadence: heartbeat every ~60s; poll telegram continuously
        last_hb = 0.0
        while not stop:
            now = time.time()
            if now - last_hb >= 60:
                try:
                    heartbeat(conn, ORG_ID)
                    print("✓ heartbeat", flush=True)
                except Exception as e:
                    print(f"DB error: {e}", flush=True)
                last_hb = now

            # run a short poll tick (non-blocking-ish)
            try:
                # one quick poll iteration (keep loop responsive)
                r = requests.get(
                    f"{API}/getUpdates",
                    params={"timeout": 0, "allowed_updates": ["message"]},
                    timeout=5,
                )
                data = r.json()
                if data.get("ok"):
                    for upd in data.get("result", []):
                        # immediately handle and ack
                        msg = upd.get("message") or {}
                        chat = msg.get("chat") or {}
                        chat_id = chat.get("id")
                        txt = (msg.get("text") or "").strip().lower()
                        if chat_id:
                            if txt in ("/start", "start", "hi", "hello"):
                                tg_send(chat_id, "🦁 online")
                            elif txt.startswith("/ping") or txt == "ping":
                                tg_send(chat_id, "🦁 pong")
                    # advance offset in a separate long-poll loop if you prefer
                else:
                    print(f"getUpdates not ok: {data}", flush=True)
            except Exception as e:
                print(f"poll tick error: {e}", flush=True)

            time.sleep(1)

    print("Shutdown clean.", flush=True)


if __name__ == "__main__":
    main()

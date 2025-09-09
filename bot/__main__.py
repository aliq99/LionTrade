# bot/__main__.py
import os
import signal
import sys
import time

import psycopg
import requests

DB_URL = os.environ.get("DATABASE_URL")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not DB_URL:
    print("ERROR: DATABASE_URL not set", flush=True)
    sys.exit(1)
if not TG_TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set", flush=True)
    sys.exit(1)

stop = False


def _sigterm(_s, _f):
    global stop
    stop = True


signal.signal(signal.SIGINT, _sigterm)
signal.signal(signal.SIGTERM, _sigterm)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_heartbeats(
              id bigserial primary key,
              ts timestamptz not null default now()
            );
        """
        )
        cur.execute(
            """
            create table if not exists bot_kv(
              key text primary key,
              val text not null
            );
        """
        )
    conn.commit()


def kv_get(conn, key):
    with conn.cursor() as cur:
        cur.execute("select val from bot_kv where key=%s;", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def kv_set(conn, key, val):
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_kv(key, val) values(%s,%s)
            on conflict(key) do update set val=excluded.val;
        """,
            (key, val),
        )


def heartbeat(conn):
    with conn.cursor() as cur:
        cur.execute("insert into bot_heartbeats default values;")


def handle_update(sess, base, upd):
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text.startswith("/start"):
        reply = "LionTrader online. Send a message to test."
    else:
        reply = f"Echo: {text}" if text else "OK"

    try:
        sess.post(
            f"{base}/sendMessage", json={"chat_id": chat_id, "text": reply}, timeout=10
        )
    except Exception as e:
        print(f"send error: {e}", flush=True)


def main():
    print("Connecting...", flush=True)
    with psycopg.connect(DB_URL, autocommit=False) as conn:
        ensure_schema(conn)
        sess = requests.Session()
        base = f"https://api.telegram.org/bot{TG_TOKEN}"

        # resume from last offset
        try:
            offset = int(kv_get(conn, "tg_update_offset") or "0")
        except ValueError:
            offset = 0

        print("Connected. Entering loop.", flush=True)
        last_hb = 0.0
        while not stop:
            try:
                # heartbeat every 60s
                now = time.time()
                if now - last_hb >= 60:
                    heartbeat(conn)
                    last_hb = now
                    print("✓ heartbeat", flush=True)

                r = sess.get(
                    f"{base}/getUpdates",
                    params={
                        "timeout": 30,
                        "offset": offset,
                        "allowed_updates": ["message"],
                    },
                    timeout=35,
                )
                data = (
                    r.json()
                    if r.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                if not data.get("ok", False):
                    print(f"poll not ok: {data}", flush=True)
                    time.sleep(5)
                    continue

                results = data.get("result", [])
                for upd in results:
                    handle_update(sess, base, upd)
                    offset = max(offset, upd.get("update_id", 0) + 1)

                if results:
                    kv_set(conn, "tg_update_offset", str(offset))
                    conn.commit()

            except Exception as e:
                print(f"poll error: {e}", flush=True)
                time.sleep(5)

    print("Shutdown clean.", flush=True)


if __name__ == "__main__":
    main()

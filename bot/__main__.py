# bot/__main__.py
import os
import signal
import sys
import time
from typing import Any, Dict, Optional

import psycopg
import requests

DB_URL = os.environ.get("DATABASE_URL")
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ORG_ID = os.environ.get("ORG_ID")  # optional; can be NULL in DB

if not DB_URL:
    print("ERROR: DATABASE_URL not set", flush=True)
    sys.exit(1)
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set", flush=True)
    sys.exit(1)

API = f"https://api.telegram.org/bot{TOKEN}"
STOP = False


def _sig_handler(_sig, _frm):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)


def ensure_schema() -> None:
    """Create heartbeat table if it doesn't exist (safe to run repeatedly)."""
    ddl = """
    create table if not exists public.heartbeat (
        id bigserial primary key,
        ts timestamptz not null default now(),
        org_id uuid null
    );
    """
    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
    except Exception as e:  # noqa: BLE001
        print(f"schema init failed: {e}", flush=True)


def write_heartbeat() -> None:
    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into public.heartbeat (org_id) values (%s)",
                    (ORG_ID,),
                )
        print(f"✓ heartbeat org={ORG_ID}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"heartbeat insert failed: {e}", flush=True)


def tg_get(method: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        r = requests.get(f"{API}/{method}", params=params, timeout=35)
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": f"request error: {e}"}


def tg_post(method: str, *, data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        r = requests.post(f"{API}/{method}", data=data, timeout=35)
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": f"request error: {e}"}


def handle_update(upd: Dict[str, Any]) -> None:
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id or not text:
        return

    if text.startswith("/ping"):
        tg_post("sendMessage", data={"chat_id": chat_id, "text": "🦁 pong"})
    elif text.lower() in {"hi", "hello"}:
        tg_post("sendMessage", data={"chat_id": chat_id, "text": "🦁 online"})


def main() -> None:
    print("Connecting...", flush=True)

    ensure_schema()

    # make sure no webhook is set (so long polling works)
    tg_get("deleteWebhook")

    print("Connected. Entering loop.", flush=True)

    next_hb = time.monotonic()  # send immediately
    offset: Optional[int] = None

    while not STOP:
        # heartbeat every 60s
        now = time.monotonic()
        if now >= next_hb:
            write_heartbeat()
            next_hb = now + 60

        # telegram long-polling (shorter than 60s so hb can trigger)
        res = tg_get(
            "getUpdates",
            params={
                "timeout": 20,  # seconds (server long-poll)
                **({"offset": offset} if offset is not None else {}),
            },
        )

        if res.get("ok"):
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                handle_update(upd)
        else:
            # common cases: Unauthorized (bad token) or Not Found (malformed URL)
            desc = res.get("description")
            code = res.get("error_code")
            print(
                f"getUpdates not ok: {{'ok': False, 'error_code': {code}, 'description': '{desc}'}}",
                flush=True,
            )
            time.sleep(3)

    print("Shutdown clean.", flush=True)


if __name__ == "__main__":
    main()

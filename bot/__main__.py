import os
import signal
import sys
import time

import psycopg

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("ERROR: DATABASE_URL not set", flush=True)
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
            """create table if not exists bot_heartbeats(
            id bigserial primary key, ts timestamptz not null default now()
        );"""
        )
    conn.commit()


def heartbeat(conn):
    with conn.cursor() as cur:
        cur.execute("insert into bot_heartbeats default values;")
    conn.commit()


def main():
    print("Connecting...", flush=True)
    with psycopg.connect(DB_URL, autocommit=False) as conn:
        ensure_schema(conn)
        print("Connected. Entering loop.", flush=True)
        while not stop:
            try:
                heartbeat(conn)
                print("✓ heartbeat", flush=True)
            except Exception as e:
                print(f"DB error: {e}", flush=True)
                time.sleep(5)
            time.sleep(60)
    print("Shutdown clean.", flush=True)


if __name__ == "__main__":
    main()

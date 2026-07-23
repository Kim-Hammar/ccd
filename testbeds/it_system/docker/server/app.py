"""
Flask web-service replica for the IT-system testbed (server n_i). Each ``/work``
request performs an upsert + read against the shared PostgreSQL database, so a request
completes iff the n_i -> db link is open. Monotonic counters derive the causal
variables: ``requests_received`` (arrivals), ``requests_completed_db`` -> Tt_i,
``responses_ok`` (2xx to the gateway). Counters live in process memory -- gunicorn
runs a single worker so they stay coherent. ``/metrics`` returns an atomic snapshot.
"""

from __future__ import annotations
import os
import threading
import time
import psycopg
from flask import Flask, jsonify

SERVER_ID = int(os.environ.get("SERVER_ID", "1"))
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_USER = os.environ.get("DB_USER", "ccd")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "ccd")
DB_NAME = os.environ.get("DB_NAME", "ccd")
DB_CONNECT_TIMEOUT = float(os.environ.get("DB_CONNECT_TIMEOUT", "1.0"))

app = Flask(__name__)

_lock = threading.Lock()
_counters = {"requests_received": 0, "requests_completed_db": 0, "responses_ok": 0}


def _dsn() -> str:
    return (f"host={DB_HOST} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} "
            f"connect_timeout={int(max(1, DB_CONNECT_TIMEOUT))}")


def _touch_db() -> bool:
    """Upsert and read this server's row; True iff the db round-trip succeeds.
    A short-lived connection per request makes a closed n_i -> db link (iptables
    REJECT) surface immediately as a failure rather than a hang."""
    try:
        with psycopg.connect(_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO app_state (server_id, counter, updated_at) "
                    "VALUES (%s, 1, now()) "
                    "ON CONFLICT (server_id) DO UPDATE SET counter = app_state.counter + 1, "
                    "updated_at = now() RETURNING counter",
                    (SERVER_ID,),
                )
                cur.fetchone()
            conn.commit()
        return True
    except Exception:
        return False


@app.route("/work", methods=["GET", "POST"])
def work():
    with _lock:
        _counters["requests_received"] += 1
    ok = _touch_db()
    with _lock:
        if ok:
            _counters["requests_completed_db"] += 1
            _counters["responses_ok"] += 1
    if ok:
        return jsonify(server_id=SERVER_ID, ok=True), 200
    return jsonify(server_id=SERVER_ID, ok=False), 503


@app.route("/metrics")
def metrics():
    with _lock:
        snapshot = dict(_counters)
    snapshot["server_id"] = SERVER_ID
    snapshot["t"] = time.time()
    return jsonify(snapshot)


@app.route("/health")
def health():
    return jsonify(server_id=SERVER_ID, ok=_touch_db())

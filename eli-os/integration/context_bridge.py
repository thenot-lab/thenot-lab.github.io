#!/usr/bin/env python3
"""
Eli/Ellie context bridge — the on-device "Connect (Data)" spine.

This is the missing link between the two halves that already exist:

  [Eli Companion APK]  --captures-->  device context (notifications, app
                                       usage, messages, sensors, share)
  [Elli-Device / SLM]  --chats + acts on the device via tool_router :8081

Today the companion ships everything to the *host* bridge; the on-device
model (Ellie) can act on the phone but cannot *see* any of that captured
context. This module closes the loop entirely on-device:

  1. It stores captured events in a local SQLite DB (loopback-only).
  2. It distills a small set of *honest, deterministic* "inferenced memory"
     facts from those events (no fabrication — every fact is derivable from
     a real row and carries a confidence + provenance).
  3. It exposes read tools with the SAME contract tool_router already uses
     ({"tier","rc","out"}), so they drop straight into tool_router.TOOLS
     and Ellie can call them mid-chat.
  4. It assembles a compact "context digest" for injection into the chat
     system prompt so Ellie is grounded in the device's current state
     without the model having to call a tool first.

Design rules carried verbatim from tool_router.py (keep the two consistent):
  * stdlib only — survives a minimal Termux, no pip deps.
  * loopback is NOT a security boundary -> bearer token required, fail-closed.
  * honesty: a tool result reports what is actually in the store, never a
    fabricated "done". Inference is bounded to what the rows literally say.
  * the floor holds: this module is READ-mostly. The only writes are into
    its own context DB. It never actuates the device (that stays in
    tool_router's ACT/PRIV tiers) and never moves data off-device.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config (env-overridable, mirrors tool_router) --------------------------
DB_PATH     = os.environ.get("ELLI_CONTEXT_DB", os.path.expanduser("~/.elli/context.db"))
BIND_HOST   = os.environ.get("ELLI_CTX_BIND_HOST", "127.0.0.1")
BIND_PORT   = int(os.environ.get("ELLI_CTX_BIND_PORT", "8082"))
AUTH_TOKEN  = os.environ.get("ELLI_AUTH_TOKEN", "")   # empty => refuse all (fail-closed)
MAX_BODY    = int(os.environ.get("ELLI_CTX_MAX_BODY", str(1 << 20)))  # 1 MiB
RETAIN_DAYS = int(os.environ.get("ELLI_CTX_RETAIN_DAYS", "30"))

# Event types the companion app already emits (see mTLSClient.postEvent /
# postObserverEvent). We ingest them verbatim; unknown types are stored too
# so a new capture surface needs no change here.
KNOWN_TYPES = (
    "notification", "usage_snapshot", "sms", "share", "screenshot",
    "observer_event", "package_installed", "package_removed", "location",
    "call", "sensor",
)


# ---- store ------------------------------------------------------------------
class ContextStore:
    """SQLite-backed on-device context + inferenced-memory store.

    Two tables:
      events  — raw captured events, exactly as the companion sent them.
      memory  — distilled durable facts (kind/key/value/confidence/source),
                superseded-in-place so the newest fact for a key wins.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts REAL NOT NULL,"
                " iso TEXT NOT NULL,"
                " type TEXT NOT NULL,"
                " payload TEXT NOT NULL)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, ts)")
            c.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts REAL NOT NULL,"
                " kind TEXT NOT NULL,"
                " key TEXT NOT NULL,"
                " value TEXT NOT NULL,"
                " confidence REAL NOT NULL,"
                " source TEXT NOT NULL,"
                " superseded INTEGER NOT NULL DEFAULT 0)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key, superseded)")

    # -- ingest ---------------------------------------------------------------
    def ingest(self, event: dict) -> dict:
        """Store one captured event and run bounded inference over it.

        `event` mirrors the companion wire shape:
          {device_id?, cert_fingerprint_sha256?, ts?, type, payload}
        Returns {"stored": bool, "id": int, "derived": [<memory keys>]}.
        """
        etype = str(event.get("type", "")).strip() or "unknown"
        payload = event.get("payload", {})
        if not isinstance(payload, (dict, list, str, int, float)) and payload is not None:
            payload = str(payload)
        iso = str(event.get("ts") or _now_iso())
        ts = _iso_to_epoch(iso)
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events(ts, iso, type, payload) VALUES(?,?,?,?)",
                (ts, iso, etype, json.dumps(payload)),
            )
            event_id = int(cur.lastrowid)
        derived = self._infer(etype, payload, iso)
        return {"stored": True, "id": event_id, "derived": derived}

    # -- inferenced memory (honest, deterministic) ----------------------------
    def _infer(self, etype: str, payload, iso: str) -> list:
        """Derive durable facts from a single event. Every fact is directly
        readable from the event — nothing is invented. Returns the keys set."""
        keys: list = []
        if etype == "usage_snapshot" and isinstance(payload, dict):
            top = str(payload.get("top_apps", ""))
            first = top.split("|")[0] if top else ""
            pkg = first.split(":")[0] if first else ""
            if pkg:
                self.remember("routine", "most_used_app", pkg, 0.7,
                              f"usage_snapshot@{iso}")
                keys.append("most_used_app")
        elif etype == "notification" and isinstance(payload, dict):
            app = str(payload.get("package", payload.get("app", "")))
            if app:
                key = f"notifs_from:{app}"
                n = self._current_int(key) + 1
                self.remember("activity", key, str(n), 0.9, f"notification@{iso}")
                keys.append(key)
        elif etype in ("sms", "share") and isinstance(payload, dict):
            who = str(payload.get("sender", payload.get("title", ""))).strip()
            if who:
                self.remember("contact", "last_contacted", who, 0.8,
                              f"{etype}@{iso}")
                keys.append("last_contacted")
        return keys

    def _current_int(self, key: str) -> int:
        """The current (non-superseded) integer value for an exact key, or 0."""
        with self._conn() as c:
            row = c.execute(
                "SELECT value FROM memory WHERE key=? AND superseded=0"
                " ORDER BY ts DESC LIMIT 1",
                (key,),
            ).fetchone()
        return int(row["value"]) if row and str(row["value"]).isdigit() else 0

    def remember(self, kind: str, key: str, value: str, confidence: float,
                 source: str) -> None:
        """Write a fact, superseding any prior fact for the same key."""
        with self._conn() as c:
            c.execute("UPDATE memory SET superseded=1 WHERE key=? AND superseded=0", (key,))
            c.execute(
                "INSERT INTO memory(ts, kind, key, value, confidence, source, superseded)"
                " VALUES(?,?,?,?,?,?,0)",
                (time.time(), kind, key, value, float(confidence), source),
            )

    def recall(self, query: str = "", limit: int = 20) -> list:
        with self._conn() as c:
            if query:
                rows = c.execute(
                    "SELECT kind,key,value,confidence,source FROM memory"
                    " WHERE superseded=0 AND (key LIKE ? OR value LIKE ?)"
                    " ORDER BY ts DESC LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT kind,key,value,confidence,source FROM memory"
                    " WHERE superseded=0 ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # -- queries used by the tools -------------------------------------------
    def recent(self, etype: str | None, limit: int) -> list:
        with self._conn() as c:
            if etype:
                rows = c.execute(
                    "SELECT iso,type,payload FROM events WHERE type=? ORDER BY ts DESC LIMIT ?",
                    (etype, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT iso,type,payload FROM events ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        out = []
        for r in rows:
            try:
                pl = json.loads(r["payload"])
            except (ValueError, TypeError):
                pl = r["payload"]
            out.append({"ts": r["iso"], "type": r["type"], "payload": pl})
        return out

    def search(self, query: str, limit: int) -> list:
        q = f"%{query}%"
        with self._conn() as c:
            rows = c.execute(
                "SELECT iso,type,payload FROM events WHERE payload LIKE ?"
                " ORDER BY ts DESC LIMIT ?",
                (q, limit),
            ).fetchall()
        return [{"ts": r["iso"], "type": r["type"], "payload": r["payload"][:400]} for r in rows]

    def usage_summary(self, window_hours: int = 24, top_n: int = 8) -> list:
        """Aggregate foreground time per app across usage_snapshot events in
        the window. Returns [{package, ms}] descending."""
        since = time.time() - window_hours * 3600
        totals: Counter = Counter()
        with self._conn() as c:
            rows = c.execute(
                "SELECT payload FROM events WHERE type='usage_snapshot' AND ts>=?",
                (since,),
            ).fetchall()
        for r in rows:
            try:
                pl = json.loads(r["payload"])
            except (ValueError, TypeError):
                continue
            top = str(pl.get("top_apps", "")) if isinstance(pl, dict) else ""
            for chunk in top.split("|"):
                parts = chunk.split(":")
                if len(parts) >= 2 and parts[1].isdigit():
                    totals[parts[0]] = max(totals[parts[0]], int(parts[1]))
        return [{"package": p, "ms": m} for p, m in totals.most_common(top_n)]

    def digest(self, max_items: int = 6) -> str:
        """Compact human-readable snapshot for system-prompt injection."""
        lines = []
        usage = self.usage_summary()
        if usage:
            top = ", ".join(f"{u['package']} ({u['ms'] // 60000}m)" for u in usage[:3])
            lines.append(f"Most-used apps (24h): {top}")
        notifs = self.recent("notification", 5)
        if notifs:
            apps = Counter()
            for n in notifs:
                pl = n["payload"]
                if isinstance(pl, dict):
                    apps[str(pl.get("package", pl.get("app", "?")))] += 1
            if apps:
                lines.append("Recent notifications: " +
                             ", ".join(f"{a}×{c}" for a, c in apps.most_common(3)))
        mem = self.recall(limit=max_items)
        for m in mem[:max_items]:
            lines.append(f"- {m['key']}: {m['value']} (conf {m['confidence']:.2f})")
        if not lines:
            return "No device context captured yet."
        return "DEVICE CONTEXT (on-device, private):\n" + "\n".join(lines)

    def prune(self, retain_days: int = RETAIN_DAYS) -> int:
        cutoff = time.time() - retain_days * 86400
        with self._conn() as c:
            cur = c.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            return cur.rowcount


# ---- tool surface (same contract as tool_router.TOOLS) ----------------------
# Each returns {"tier","rc","out"}. tier is READ for everything here: this
# module only observes captured context, it never actuates the device.
def make_tools(store: ContextStore) -> dict:
    def t_recent_notifications(args):
        limit = _clamp_int(args.get("limit", 10), 1, 50)
        rows = store.recent("notification", limit)
        return {"tier": "READ", "rc": 0, "out": json.dumps(rows)[:4000]}

    def t_usage_summary(args):
        window = _clamp_int(args.get("window_hours", 24), 1, 168)
        rows = store.usage_summary(window)
        return {"tier": "READ", "rc": 0, "out": json.dumps(rows)[:4000]}

    def t_recent_messages(args):
        limit = _clamp_int(args.get("limit", 10), 1, 50)
        sms = store.recent("sms", limit)
        share = store.recent("share", limit)
        return {"tier": "READ", "rc": 0,
                "out": json.dumps({"sms": sms, "share": share})[:4000]}

    def t_search_context(args):
        q = str(args.get("query", "")).strip()
        if not q:
            return {"tier": "READ", "rc": 2, "out": "missing query"}
        limit = _clamp_int(args.get("limit", 10), 1, 50)
        return {"tier": "READ", "rc": 0, "out": json.dumps(store.search(q, limit))[:4000]}

    def t_context_digest(_args):
        return {"tier": "READ", "rc": 0, "out": store.digest()}

    def t_recall(args):
        q = str(args.get("query", "")).strip()
        return {"tier": "READ", "rc": 0, "out": json.dumps(store.recall(q))[:4000]}

    return {
        "recent_notifications": t_recent_notifications,
        "usage_summary": t_usage_summary,
        "recent_messages": t_recent_messages,
        "search_context": t_search_context,
        "context_digest": t_context_digest,
        "recall": t_recall,
    }


CONTEXT_TOOL_SPEC = (
    "  context_digest{}                    -> snapshot of current device state\n"
    "  recent_notifications{limit?}        -> recent notifications the phone got\n"
    "  usage_summary{window_hours?}        -> per-app foreground time\n"
    "  recent_messages{limit?}             -> recent SMS + shared text\n"
    "  search_context{query,limit?}        -> keyword search over captured events\n"
    "  recall{query?}                      -> durable facts Ellie has inferred\n"
)


# ---- helpers ----------------------------------------------------------------
def _clamp_int(v, lo, hi) -> int:
    try:
        n = int(v)
    except (ValueError, TypeError):
        n = lo
    return max(lo, min(hi, n))


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_to_epoch(iso: str) -> float:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(iso.split("+")[0].rstrip("Z"), fmt.rstrip("Z")))
        except (ValueError, TypeError):
            continue
    return time.time()


# ---- HTTP surface (loopback, bearer, fail-closed) ---------------------------
class Handler(BaseHTTPRequestHandler):
    store: ContextStore = None      # set by main()
    tools: dict = None

    def _auth_ok(self) -> bool:
        if not AUTH_TOKEN:
            return False            # fail-closed
        got = self.headers.get("Authorization", "")
        return hmac.compare_digest(got, f"Bearer {AUTH_TOKEN}")

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "db": self.store.db_path})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth_ok():
            return self._send(401, {"error": "unauthorized"})
        n = int(self.headers.get("Content-Length", "0"))
        if n > MAX_BODY:
            return self._send(413, {"error": "body too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        path = self.path.rstrip("/")
        if path == "/v1/context/event":
            return self._send(200, self.store.ingest(body))
        if path == "/v1/context/tool":
            name = body.get("name", "")
            fn = self.tools.get(name)
            if not fn:
                return self._send(404, {"error": f"unknown tool: {name}"})
            return self._send(200, fn(body.get("args", {}) or {}))
        if path == "/v1/context/digest":
            return self._send(200, {"digest": self.store.digest()})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    store = ContextStore()
    Handler.store = store
    Handler.tools = make_tools(store)
    if not AUTH_TOKEN:
        print("[elli-ctx] WARNING: ELLI_AUTH_TOKEN unset — refusing all requests (fail-closed).")
    print(f"[elli-ctx] context bridge on {BIND_HOST}:{BIND_PORT} db={store.db_path}")
    ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

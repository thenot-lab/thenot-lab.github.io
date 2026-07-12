#!/usr/bin/env python3
"""Eli OS memory layer — Phase 2 (roadmap: eli-os/plans/roadmap.md).

Three stores from memory/context_memory_spec.md, stdlib only (SQLite + pure
Python), so the whole thing runs single-admin on a home box:

- ShortTermStore  : conversation state + working set for one task (SQLite).
- LongTermStore   : durable decisions/playbooks/findings, semantic search
                    over a pluggable embedding (default: deterministic hashing
                    embed, so it works offline; swap embed_fn for a real model).
- PolicyStore     : users, force-top-tier rules, budgets (JSON seed in repo).

Plus assemble_handoff(): the escalation payload that carries the **full**
short-term trace (every intermediate output + confidence) up to the top tier —
never a summary, per the spec's "never hand up a summary" rule.
"""

import hashlib
import json
import math
import os
import sqlite3
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("ELI_MEMORY_DB", HERE / "eli_memory.db"))
DEFAULT_POLICY_SEED = Path(os.environ.get("ELI_POLICY_SEED", HERE / "policy_seed.json"))
EMBED_DIM = 256


# --------------------------------------------------------------------------- #
# Embedding — deterministic, offline, pluggable.
# --------------------------------------------------------------------------- #
def hash_embed(text, dim=EMBED_DIM):
    """Character-trigram hashing into an L2-normalized vector.

    Not a semantic model — it captures lexical overlap, which is enough to
    make retrieval testable and the interface real. Replace with a call to an
    embedding model (same signature: str -> list[float]) when one is wired in.
    """
    vec = [0.0] * dim
    t = (text or "").lower()
    if not t:
        return vec
    padded = f"  {t}  "
    for i in range(len(padded) - 2):
        gram = padded[i:i + 3]
        h = int(hashlib.blake2b(gram.encode(), digest_size=8).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def cosine(a, b):
    # embed_fn is pluggable; a dimension mismatch (two different models) would
    # otherwise let zip() silently truncate to a meaningless-but-valid score.
    if len(a) != len(b):
        raise ValueError(f"embedding dimension mismatch: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b))  # inputs are already L2-normalized


# --------------------------------------------------------------------------- #
# Connection / schema
# --------------------------------------------------------------------------- #
def connect(db_path=None):
    conn = sqlite3.connect(str(db_path or DEFAULT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_schema(conn)
    return conn


def _init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS short_term (
            session_id TEXT PRIMARY KEY,
            project TEXT, task_id TEXT, current_node TEXT, cache_key TEXT,
            messages TEXT NOT NULL DEFAULT '[]',
            intermediate_outputs TEXT NOT NULL DEFAULT '[]',
            active_constraints TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS long_term (
            id TEXT PRIMARY KEY, project TEXT, type TEXT, title TEXT,
            text TEXT NOT NULL, embedding TEXT NOT NULL, source TEXT,
            created_at REAL NOT NULL, supersedes TEXT, superseded INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS ix_long_term_project ON long_term(project, superseded);
        """
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Short-term store
# --------------------------------------------------------------------------- #
class ShortTermStore:
    """Working set for one task. Shared across tiers so escalation carries it."""

    # `column` is interpolated into SQL below, so it must never be caller-
    # controlled — only these internal JSON-array columns may be appended to.
    _APPENDABLE_COLUMNS = {"messages", "intermediate_outputs"}

    def __init__(self, conn):
        self.conn = conn

    def create_session(self, session_id, project=None, task_id=None,
                       cache_key=None, active_constraints=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO short_term "
            "(session_id, project, task_id, cache_key, active_constraints, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, project, task_id, cache_key,
             json.dumps(active_constraints or []), time.time()),
        )
        self.conn.commit()

    def append_message(self, session_id, role, content):
        self._append(session_id, "messages", {"role": role, "content": content})

    def append_output(self, session_id, node, tier, output, confidence):
        """Record a node's result AND its confidence — the confidence is the
        signal escalation reads, so it is stored, never dropped."""
        self._append(session_id, "intermediate_outputs",
                     {"node": node, "tier": tier, "output": output,
                      "confidence": confidence})

    def set_current_node(self, session_id, node):
        self.conn.execute(
            "UPDATE short_term SET current_node=?, updated_at=? WHERE session_id=?",
            (node, time.time(), session_id))
        self.conn.commit()

    def _append(self, session_id, column, item):
        if column not in self._APPENDABLE_COLUMNS:
            raise ValueError(f"column {column!r} is not appendable")
        row = self.conn.execute(
            f"SELECT {column} FROM short_term WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no session {session_id!r}")
        items = json.loads(row[column])
        items.append(item)
        self.conn.execute(
            f"UPDATE short_term SET {column}=?, updated_at=? WHERE session_id=?",
            (json.dumps(items), time.time(), session_id))
        self.conn.commit()

    def get(self, session_id):
        row = self.conn.execute(
            "SELECT * FROM short_term WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for col in ("messages", "intermediate_outputs", "active_constraints"):
            d[col] = json.loads(d[col])
        return d

    def evict(self, session_id):
        self.conn.execute("DELETE FROM short_term WHERE session_id=?", (session_id,))
        self.conn.commit()


# --------------------------------------------------------------------------- #
# Long-term vector store
# --------------------------------------------------------------------------- #
class LongTermStore:
    """Durable knowledge retrieved by semantic search at task start."""

    def __init__(self, conn, embed_fn=hash_embed):
        self.conn = conn
        self.embed_fn = embed_fn

    def write(self, project, record_type, title, text, source=None, supersedes=None):
        rec_id = "mem_" + hashlib.blake2b(
            f"{project}|{title}|{text}|{time.time()}".encode(), digest_size=8
        ).hexdigest()
        emb = json.dumps(self.embed_fn(f"{title}\n{text}"))
        self.conn.execute(
            "INSERT INTO long_term "
            "(id, project, type, title, text, embedding, source, created_at, supersedes) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (rec_id, project, record_type, title, text, emb, source, time.time(), supersedes),
        )
        # Write-back: a decision that supersedes another marks the old one, so
        # the store stays the living memory, not a stale dump.
        if supersedes:
            self.conn.execute(
                "UPDATE long_term SET superseded=1 WHERE id=?", (supersedes,))
        self.conn.commit()
        return rec_id

    def search(self, query, project=None, k=5, include_superseded=False):
        sql = "SELECT * FROM long_term"
        clauses, params = [], []
        if project:
            clauses.append("project=?")
            params.append(project)
        if not include_superseded:
            clauses.append("superseded=0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        q = self.embed_fn(query)
        scored = []
        for row in self.conn.execute(sql, params):
            score = cosine(q, json.loads(row["embedding"]))
            scored.append((score, dict(row)))
        scored.sort(key=lambda s: s[0], reverse=True)
        out = []
        for score, rec in scored[:k]:
            rec.pop("embedding", None)
            rec["score"] = round(score, 4)
            out.append(rec)
        return out


# --------------------------------------------------------------------------- #
# Profile & policy store
# --------------------------------------------------------------------------- #
class PolicyStore:
    """Who gets what, and when the top tier is mandatory. JSON seed in repo."""

    def __init__(self, seed_path=None):
        self.data = json.loads(Path(seed_path or DEFAULT_POLICY_SEED).read_text())

    def user(self, name):
        return self.data.get("users", {}).get(name)

    def top_tier_share_target(self):
        return self.data.get("policies", {}).get("top_tier_share_target")

    def daily_ceiling(self, project):
        return (self.data.get("policies", {})
                .get("budgets", {}).get("per_project_daily_token_ceiling", {})
                .get(project))

    def force_top_tier(self, task):
        """Does policy mandate top-tier review for this task, regardless of size?

        task: {output_is_security_critical?, decision_is_high_impact?,
               action_is_irreversible_and_external?}
        Returns the list of matched conditions (empty = not forced).
        """
        conditions = (self.data.get("policies", {})
                      .get("force_top_tier_review_when", []))
        return [c for c in conditions if task.get(c)]


# --------------------------------------------------------------------------- #
# Escalation handoff — never a summary
# --------------------------------------------------------------------------- #
def assemble_handoff(session_id, shortterm, longterm, reason, project=None):
    """Build the top-tier escalation payload in cache-friendly order.

    1. cache_key reference (stable prefix — cached, not re-sent inline)
    2. FULL short-term context: every intermediate output AND its confidence
    3. relevant long-term memory (prior decisions on this surface)
    4. the escalation reason (which trigger fired)

    The contradictions between low-confidence outputs are the signal, so the
    full trace goes up verbatim — summarizing would discard exactly what
    triggered the escalation.
    """
    ctx = shortterm.get(session_id)
    if ctx is None:
        raise KeyError(f"no session {session_id!r}")
    query = " ".join(
        str(o.get("output", "")) for o in ctx["intermediate_outputs"]
    ) or (ctx["messages"][-1]["content"] if ctx["messages"] else "")
    memory = longterm.search(query, project=project or ctx.get("project"), k=5)
    return {
        "cache_key": ctx.get("cache_key"),
        "short_term_context": {
            "messages": ctx["messages"],
            "intermediate_outputs": ctx["intermediate_outputs"],  # full, with confidence
            "active_constraints": ctx["active_constraints"],
        },
        "relevant_memory": memory,
        "escalation_reason": reason,
        "is_summary": False,
    }


if __name__ == "__main__":
    # Tiny demo run.
    conn = connect(":memory:")
    st = ShortTermStore(conn)
    st.create_session("s1", project="eli_guardian", cache_key="k1")
    st.append_output("s1", "n3", "opus", "SQLi likely in auth.py:42", 0.55)
    st.append_output("s1", "n3b", "opus", "No — parameterized query, false positive", 0.5)
    lt = LongTermStore(conn)
    lt.write("eli_guardian", "decision", "auth.py uses parameterized queries",
             "The auth module was audited 2026-05; all queries are parameterized.")
    handoff = assemble_handoff("s1", st, lt, "conflicting_outputs_across_runs")
    print(json.dumps(handoff, indent=2))

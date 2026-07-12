#!/usr/bin/env python3
"""Eli OS task-graph engine — Phase 3 (roadmap: eli-os/plans/roadmap.md).

Implements orchestration/task_graph_spec.md: complex tasks as DAGs, run
plan -> execute -> aggregate -> review. Nodes run when every dependency is
`done` or `skipped`; a node with a `condition` that evaluates false becomes
terminal-`skipped`, and skipped satisfies downstream dependencies (so the
Guardian worked example's n5 proceeds when the top-tier n4 is skipped).

Retry policy is safety-aware: only idempotent work auto-retries; action-bearing
nodes retry only with an idempotency key; irreversible nodes never auto-retry
(they may have partially succeeded before the error). Stdlib only.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

PENDING, RUNNING, DONE, SKIPPED, FAILED, BLOCKED = (
    "pending", "running", "done", "skipped", "failed", "blocked")
TERMINAL = {DONE, SKIPPED, FAILED, BLOCKED}
SATISFYING = {DONE, SKIPPED}  # a dependency in one of these lets dependents run


class Node:
    def __init__(self, id, run, tier=None, depends_on=(), condition=None,
                 idempotent=True, irreversible=False, idempotency_key=None,
                 max_retries=2, workflow=None, title=""):
        """run(results) -> {output, confidence?, ...}. condition(results) -> bool
        decides at dispatch time whether this node runs (True) or is skipped."""
        self.id = id
        self.run = run
        self.tier = tier
        self.depends_on = list(depends_on)
        self.condition = condition
        self.idempotent = idempotent
        self.irreversible = irreversible
        self.idempotency_key = idempotency_key
        self.max_retries = max_retries
        self.workflow = workflow
        self.title = title
        self.status = PENDING
        self.result = None
        self.error = None
        self.retries = 0


class TaskGraph:
    def __init__(self, nodes, max_concurrency=4, backoff_base=0.0, review_fn=None):
        self.nodes = {n.id: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("duplicate node ids")
        self.max_concurrency = max_concurrency
        self.backoff_base = backoff_base
        self.review_fn = review_fn
        self.log = []  # ordered (node_id, status) transitions, for tests/telemetry

    # -- lifecycle ------------------------------------------------------------
    def execute(self):
        """Run the DAG to a fixed point. Returns the aggregate result dict."""
        results = {}
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            while True:
                ready = self._ready_nodes()
                if not ready:
                    break
                to_run = []
                for n in ready:
                    # Condition is evaluated once deps are resolved.
                    if n.condition is not None and not n.condition(results):
                        self._set(n, SKIPPED)
                        continue
                    to_run.append(n)
                if not to_run:
                    continue  # everything ready was skipped; re-scan for newly-ready
                futures = {pool.submit(self._run_node, n, results): n for n in to_run}
                # Record completions in actual completion order (no head-of-line
                # blocking on a slow node); the transition log reflects reality.
                for fut in as_completed(futures):
                    n = futures[fut]
                    ok, value = fut.result()
                    if ok:
                        n.result = value
                        results[n.id] = value
                        self._set(n, DONE)
                    else:
                        n.error = value
                        self._set(n, FAILED)
        self._block_unreachable()
        aggregate = {
            "results": results,
            "statuses": {nid: n.status for nid, n in self.nodes.items()},
            "log": list(self.log),
        }
        if self.review_fn is not None:
            aggregate["review"] = self.review_fn(aggregate)
        return aggregate

    # -- scheduling -----------------------------------------------------------
    def _ready_nodes(self):
        ready = []
        for n in self.nodes.values():
            if n.status != PENDING:
                continue
            dep_status = [self.nodes[d].status for d in n.depends_on]
            if any(s not in TERMINAL for s in dep_status):
                continue  # a dependency hasn't finished yet
            if all(s in SATISFYING for s in dep_status):
                ready.append(n)
            # else: a dep failed/blocked -> handled by _block_unreachable
        return ready

    def _block_unreachable(self):
        """Any node still pending after the fixed point is blocked by a failed
        (or itself-blocked) dependency — surface it, don't silently drop."""
        changed = True
        while changed:
            changed = False
            for n in self.nodes.values():
                if n.status != PENDING:
                    continue
                dep_status = [self.nodes[d].status for d in n.depends_on]
                if all(s in TERMINAL for s in dep_status) and any(
                        s in (FAILED, BLOCKED) for s in dep_status):
                    self._set(n, BLOCKED)
                    changed = True

    # -- node execution + retry policy ---------------------------------------
    def _run_node(self, n, results):
        self._set(n, RUNNING)
        attempts = self._max_attempts(n)
        last_err = None
        for attempt in range(attempts):
            try:
                return True, n.run(dict(results))
            except Exception as e:  # noqa: BLE001 — surfaced as node failure
                last_err = repr(e)
                n.retries = attempt
                if attempt + 1 < attempts and self.backoff_base:
                    time.sleep(self.backoff_base * (2 ** attempt))
        return False, last_err

    def _max_attempts(self, n):
        """1 = no auto-retry. Only idempotent work (or action-bearing work with
        an idempotency key) retries; irreversible nodes never do."""
        if n.irreversible:
            return 1
        if n.idempotent or n.idempotency_key is not None:
            return n.max_retries + 1
        return 1

    def _set(self, n, status):
        n.status = status
        self.log.append((n.id, status))


# --------------------------------------------------------------------------- #
# Guardian worked example graph builder (task_graph_spec.md).
# n4 (top-tier verdict) carries the escalation condition; when unmet it is
# skipped and n5 assembles the report without a top-tier verdict.
# --------------------------------------------------------------------------- #
def guardian_graph(executors, escalation_condition):
    """executors: dict node_id -> run(results). escalation_condition:
    condition(results) -> bool deciding whether n4 runs."""
    return TaskGraph([
        Node("n1", executors["n1"], tier="haiku", title="triage+dedup"),
        Node("n2", executors["n2"], tier="sonnet", depends_on=["n1"],
             title="STRIDE classify"),
        Node("n3", executors["n3"], tier="opus", depends_on=["n2"],
             title="semantic analysis"),
        Node("n4", executors["n4"], tier="top", depends_on=["n3"],
             condition=escalation_condition, title="contested-finding verdict"),
        Node("n5", executors["n5"], tier="sonnet", depends_on=["n2", "n3", "n4"],
             title="assemble report"),
    ])


if __name__ == "__main__":
    # Demo: n4 skipped (confident) vs run (conflict).
    def mk(execs):
        return guardian_graph(
            execs, escalation_condition=lambda r: r["n3"]["confidence"] < 0.6)

    def stub(name, conf=0.9):
        return lambda r: {"output": f"{name} ok", "confidence": conf}

    confident = {"n1": stub("n1"), "n2": stub("n2"), "n3": stub("n3", 0.9),
                 "n4": stub("n4"), "n5": stub("n5")}
    print("confident:", mk(confident).execute()["statuses"])
    contested = dict(confident, n3=stub("n3", 0.4))
    print("contested:", mk(contested).execute()["statuses"])

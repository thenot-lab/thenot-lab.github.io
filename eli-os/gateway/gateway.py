#!/usr/bin/env python3
"""Eli OS gateway — Phase 1 (roadmap: eli-os/plans/roadmap.md).

Stateless gateway: accepts a request, classifies it, routes it with
routing/model_tree.json (config, not code), calls the chosen Claude model
endpoint, and writes a telemetry record per observability/telemetry_spec.md.

Zero-dependency by design (Dominion ethos): Python stdlib only, raw HTTP
against api.anthropic.com. Swapping in the official `anthropic` SDK later is
a drop-in upgrade confined to `call_model()`.

Usage:
    python3 gateway.py route '<request-json>'          # routing decision only
    python3 gateway.py complete '<request-json>'       # route + model call
    python3 gateway.py serve [--port 8484]             # HTTP: /route /complete /healthz

Request JSON shape (the variable suffix; see brain-stack/prompts/prompt_reasoner.md):
    {
      "project": "eli_guardian",            # optional; enables project overrides
      "task_type": "finding_triage_dedup",  # optional; inferred if missing
      "risk_flags": [],                     # optional; policy store can force top tier
      "interactive": true,                  # optional; batch guard signal
      "system": "...", "prompt": "...",     # the actual content
      "max_tokens": 16000,                  # optional
      "dry_run": true                       # optional; skip the API call
    }

Env: ANTHROPIC_API_KEY (required for live calls; dry_run works without),
     ELI_TELEMETRY (JSONL path, default ./telemetry.jsonl),
     ELI_MODEL_TREE (policy path, default ../routing/model_tree.json).
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# Fable 5 safety classifiers can decline benign-adjacent security work; the
# server-side fallback re-serves the request on Opus 4.8 in the same call.
FALLBACK_BETA = "server-side-fallback-2026-06-01"
DEFAULT_MAX_TOKENS = 16000
RETRYABLE = {429, 500, 529}

HERE = Path(__file__).resolve().parent
POLICY_PATH = Path(os.environ.get("ELI_MODEL_TREE", HERE.parent / "routing" / "model_tree.json"))
TELEMETRY_PATH = Path(os.environ.get("ELI_TELEMETRY", "telemetry.jsonl"))
MAX_BODY_BYTES = 1_048_576  # 1 MiB cap on POST bodies

# Serializes JSONL appends so concurrent ThreadingHTTPServer requests can't
# interleave partial lines (which would then break top_tier_share parsing).
_TELEMETRY_LOCK = threading.Lock()
# top_tier_share() is called on every top-tier route and every /healthz probe;
# cache the scan keyed by (mtime, size) so unchanged files aren't re-read.
_SHARE_CACHE = {}

# Crude content classifier: only consulted when the caller sends no task_type.
# Explicit metadata always wins — this is a fallback, not the router.
KEYWORD_TASK_TYPES = [
    (("architecture", "strategy", "tradeoff"), "architecture_decision"),
    (("plan", "design", "build", "implement", "refactor"), "multi_step_plan"),
    (("summarize", "format", "rewrite", "translate"), "summarize"),
    (("classify", "triage", "dedup"), "triage"),
]


def load_policy(path=POLICY_PATH):
    with open(path) as f:
        return json.load(f)


def classify(request, policy):
    """Derive routing features. Explicit fields win; content heuristics fill gaps."""
    features = {
        "project": request.get("project"),
        "task_type": request.get("task_type"),
        "risk_flags": request.get("risk_flags", []),
        "interactive": request.get("interactive", True),
        "input_length": len(request.get("prompt", "") or ""),
    }
    if not features["task_type"]:
        text = (request.get("prompt") or "").lower()
        for keywords, task_type in KEYWORD_TASK_TYPES:
            if any(k in text for k in keywords):
                features["task_type"] = task_type
                break
        else:
            features["task_type"] = "chat" if features["input_length"] < 500 else "doc_operation"
    return features


def _resolve_override(value):
    """Overrides are either a tier string or {tier, batch?, workflow?}."""
    if isinstance(value, str):
        return {"tier": value, "batch": False, "workflow": None}
    return {"tier": value.get("tier"), "batch": value.get("batch", False),
            "workflow": value.get("workflow")}


def route(request, policy):
    """Apply routing/model_tree.json: overrides first, then rules top-down."""
    features = classify(request, policy)
    tiers = policy["tiers"]
    decision = {
        "request_id": request.get("request_id") or f"req_{uuid.uuid4().hex[:12]}",
        "features": features,
        "batch": False,
        "workflow": None,
        "alerts": [],
    }

    # 1. Project overrides (most specific).
    overrides = policy.get("project_overrides", {}).get(features["project"] or "", {})
    if features["task_type"] in overrides:
        resolved = _resolve_override(overrides[features["task_type"]])
        # escalation_only entries gate top-tier access; they are not routes.
        if resolved["tier"] in tiers:
            decision.update(tier=resolved["tier"], batch=resolved["batch"],
                            workflow=resolved["workflow"],
                            route_reason=f"project_override:{features['project']}/{features['task_type']}")
            return _finish(decision, tiers, features)

    # 2. Policy rules, top-down; first match wins.
    for rule in policy["rules"]:
        match = rule.get("match", {})
        flags = match.get("risk_flags")
        if flags is not None:
            if any(f in features["risk_flags"] for f in flags):
                decision.update(tier=rule["route"], route_reason=f"rule:risk_flags:{flags}")
                return _finish(decision, tiers, features)
            continue
        types = match.get("task_type")
        if types is not None:
            if features["task_type"] in types:
                req_files = match.get("requires_files")
                if req_files is not None and request.get("requires_files", False) != req_files:
                    continue
                decision.update(tier=rule["route"], route_reason=f"rule:task_type:{features['task_type']}")
                return _finish(decision, tiers, features)
            continue
        decision.update(tier=rule["route"], route_reason="rule:default")
        return _finish(decision, tiers, features)

    decision.update(tier="sonnet", route_reason="fallback:hardcoded_default")
    return _finish(decision, tiers, features)


def _finish(decision, tiers, features):
    decision["model"] = tiers[decision["tier"]]["model"]
    if decision["tier"] == "top":
        share = top_tier_share()
        if share is not None and share > 0.15:
            decision["alerts"].append(f"budget_guard:top_tier_share={share:.2f}>0.15")
    if not features["interactive"] and not decision["batch"]:
        decision["alerts"].append("budget_guard:non_interactive_consider_batch")
    return decision


def check_escalation(signals, policy):
    """Opus→top escalation triggers per routing/model_tree.json#escalation.

    signals: {confidence?, iterations?, conflicting_runs?, constraint_conflict?}
    Returns the list of canonical trigger names that fired.
    """
    fired = []
    if signals.get("confidence") is not None and signals["confidence"] < 0.6:
        fired.append("self_reported_confidence")
    if signals.get("iterations", 0) >= 3:
        fired.append("iterations_without_convergence")
    if signals.get("conflicting_runs", 0) >= 2:
        fired.append("conflicting_outputs_across_runs")
    if signals.get("constraint_conflict"):
        fired.append("constraint_conflict_detected")
    return fired


def build_payload(decision, request):
    """Assemble the Messages API body with per-tier thinking/effort config."""
    payload = {
        "model": decision["model"],
        "max_tokens": request.get("max_tokens", DEFAULT_MAX_TOKENS),
        "messages": [{"role": "user", "content": request.get("prompt", "")}],
    }
    if request.get("system"):
        # Cache-friendly: the stable prefix goes in system with a cache marker
        # (brain-stack/cache/cache_key_schema.md). Callers pass the assembled
        # prefix; the variable suffix is the user message.
        payload["system"] = [{"type": "text", "text": request["system"],
                              "cache_control": {"type": "ephemeral"}}]
    tier = decision["tier"]
    if tier in ("opus", "sonnet"):
        payload["thinking"] = {"type": "adaptive"}
        payload["output_config"] = {"effort": "high"}
    elif tier == "top":
        # Fable 5: thinking always on — omit the param; effort controls depth.
        payload["output_config"] = {"effort": "high"}
        payload["fallbacks"] = [{"model": "claude-opus-4-8"}]
    return payload


def call_model(decision, request, api_key=None, max_retries=2):
    """POST /v1/messages via stdlib urllib, with retry on 429/5xx."""
    if request.get("dry_run"):
        return {"dry_run": True, "payload": build_payload(decision, request)}
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set (use dry_run for offline routing)")
    payload = build_payload(decision, request)
    headers = {"Content-Type": "application/json", "x-api-key": api_key,
               "anthropic-version": API_VERSION}
    if decision["tier"] == "top":
        headers["anthropic-beta"] = FALLBACK_BETA
    body = json.dumps(payload).encode()
    last_err = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {detail[:500]}")
            if e.code not in RETRYABLE or attempt == max_retries:
                raise last_err from e
            time.sleep(_retry_after(e.headers.get("retry-after"), attempt))
        except urllib.error.URLError as e:
            last_err = RuntimeError(f"connection error: {e.reason}")
            if attempt == max_retries:
                raise last_err from e
            time.sleep(2 ** (attempt + 1))
    raise last_err


def _retry_after(header, attempt):
    """Retry-After is delta-seconds or an HTTP-date; fall back to backoff."""
    backoff = 2 ** (attempt + 1)
    if not header:
        return backoff
    try:
        return float(header)
    except ValueError:
        pass
    try:
        delta = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(delta, 60.0))  # clamp to a sane ceiling
    except (TypeError, ValueError):
        return backoff


def extract_text(response):
    """Read the answer defensively: check stop_reason before content."""
    if response.get("dry_run"):
        return ""
    if response.get("stop_reason") == "refusal":
        details = response.get("stop_details") or {}
        return f"[refused: category={details.get('category')}]"
    return "".join(b.get("text", "") for b in response.get("content", [])
                   if b.get("type") == "text")


def write_telemetry(record, path=None):
    path = Path(path or TELEMETRY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    # Lock + a single write() keeps concurrent appends from interleaving.
    with _TELEMETRY_LOCK:
        with open(path, "a") as f:
            f.write(line)


def model_call_record(decision, request, response, latency_ms, outcome="ok",
                      escalation_trigger=None):
    """One record per model call — observability/telemetry_spec.md schema."""
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "record": "model_call",
        "request_id": decision["request_id"],
        "session_id": request.get("session_id"),
        "task_id": request.get("task_id"),
        "node_id": request.get("node_id"),
        "project": decision["features"]["project"],
        "tier": decision["tier"],
        "model": decision["model"],
        "route_reason": decision["route_reason"],
        "escalated": escalation_trigger is not None,
        "escalation_trigger": escalation_trigger,
        "tools_used": [],
        "tokens": {"in": usage.get("input_tokens", 0),
                   "out": usage.get("output_tokens", 0),
                   "cached": usage.get("cache_read_input_tokens", 0)},
        "cache_hit": usage.get("cache_read_input_tokens", 0) > 0,
        "batch": decision["batch"],
        "latency_ms": latency_ms,
        # null until later phases compute them (spec: telemetry_spec.md).
        "cost_usd": None,
        "confidence": None,
        "guardrail_flags": ["none"],
        "outcome": outcome,
    }


def gate_record(request_id, principal, kind, action, decision_str,
                reversibility="n/a", result="n/a"):
    """Gate/action event — the audit-trail record for non-model-call moments."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "record": "gate",
        "request_id": request_id,
        "session_id": None,
        "principal": principal,
        "kind": kind,
        "action": action,
        "reversibility": reversibility,
        "decision": decision_str,
        "result": result,
    }


def top_tier_share(path=None):
    """Fraction of logged model calls routed to the top tier; None if no log.

    Cached by (mtime, size): a health-probe storm or a burst of top-tier
    routes re-reads the JSONL only when it has actually changed since the last
    scan, keeping this O(1) between writes instead of O(n) per call.
    """
    path = Path(path or TELEMETRY_PATH)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    key = str(path)
    cached = _SHARE_CACHE.get(key)
    signature = (stat.st_mtime_ns, stat.st_size)
    if cached and cached[0] == signature:
        return cached[1]
    total = top = 0
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("record") != "model_call":
                continue
            total += 1
            top += rec.get("tier") == "top"
    share = (top / total) if total else None
    _SHARE_CACHE[key] = (signature, share)
    return share


def complete(request, policy):
    """Route → call model → write telemetry. Returns (decision, response).

    Always represents an intended model call, so it always writes one
    `model_call` record (a dry_run stands in for a real call and still logs).
    Route-only callers use `route()` directly and write nothing, so
    exploration traffic doesn't pollute top_tier_share / budget metrics.
    """
    decision = route(request, policy)
    start = time.monotonic()
    outcome = "ok"
    try:
        response = call_model(decision, request)
    except Exception as e:  # noqa: BLE001 — any failure is logged as outcome=failed
        outcome = "failed"
        response = {"error": str(e)}
    latency_ms = int((time.monotonic() - start) * 1000)
    write_telemetry(model_call_record(decision, request, response, latency_ms, outcome))
    return decision, response


class Handler(BaseHTTPRequestHandler):
    policy = None

    def _reply(self, code, obj):
        body = json.dumps(obj, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(200, {"ok": True, "policy_version": self.policy.get("version"),
                              "top_tier_share": top_tier_share()})
        else:
            self._reply(404, {"error": "unknown path"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._reply(400, {"error": "invalid Content-Length"})
            return
        if length > MAX_BODY_BYTES:
            self._reply(413, {"error": f"request body exceeds {MAX_BODY_BYTES} bytes"})
            return
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._reply(400, {"error": "invalid JSON"})
            return
        if self.path == "/route":
            decision = route(request, self.policy)  # route-only: no telemetry
            if request.get("signals"):
                decision["escalation_triggers"] = check_escalation(request["signals"], self.policy)
            self._reply(200, decision)
        elif self.path == "/complete":
            decision, response = complete(request, self.policy)
            self._reply(200, {"decision": decision, "response": response,
                              "text": extract_text(response) if "error" not in response else None})
        else:
            self._reply(404, {"error": "unknown path"})

    def log_message(self, fmt, *args):
        pass  # telemetry JSONL is the log of record


def main(argv):
    policy = load_policy()
    if len(argv) >= 2 and argv[1] == "serve":
        port = 8484
        if "--port" in argv:
            idx = argv.index("--port")
            if idx + 1 >= len(argv):
                print("error: --port requires a value")
                return 1
            port = int(argv[idx + 1])
        Handler.policy = policy
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        print(f"eli-os gateway on http://127.0.0.1:{port}  (policy v{policy.get('version')})")
        server.serve_forever()
    elif len(argv) >= 3 and argv[1] == "route":
        # Routing decision only — no model call, no telemetry.
        request = json.loads(argv[2])
        decision = route(request, policy)
        if request.get("signals"):
            decision["escalation_triggers"] = check_escalation(request["signals"], policy)
        print(json.dumps({"decision": decision}, indent=2))
    elif len(argv) >= 3 and argv[1] == "complete":
        request = json.loads(argv[2])
        decision, response = complete(request, policy)
        print(json.dumps({"decision": decision, "response": response,
                          "text": extract_text(response) if "error" not in response else None},
                         indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Eli OS observability dashboard — Phase 6 (roadmap: eli-os/plans/roadmap.md).

Reads the telemetry JSONL (Phase 1 model_call records + Phase 5 gate records),
computes the signals telemetry_spec.md says to watch, and renders a
self-contained HTML report. Estimated cost is computed here from a rate table —
this is the "cost pricing lands with the utilization work" that lets the
telemetry cost_usd field move from null to a number. Stdlib only.
"""

import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# $ per 1M tokens (input, output). Cached input ~0.1x input.
MODEL_RATES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
}
TOP_TIER_ALERT = 0.15
CACHE_HIT_FLOOR = 0.70


def load_records(path):
    records = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def estimate_cost(rec):
    rates = MODEL_RATES.get(rec.get("model"))
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    tok = rec.get("tokens", {})
    cached = tok.get("cached", 0)
    fresh_in = max(0, tok.get("in", 0) - cached)
    return (fresh_in * in_rate + cached * in_rate * 0.1
            + tok.get("out", 0) * out_rate) / 1_000_000


def compute_signals(records):
    calls = [r for r in records if r.get("record") == "model_call"]
    gates = [r for r in records if r.get("record") == "gate"]
    total = len(calls)
    top = sum(r.get("tier") == "top" for r in calls)
    cache_hits = sum(bool(r.get("cache_hit")) for r in calls)
    escalated = sum(bool(r.get("escalated")) for r in calls)

    cost_by_day = defaultdict(float)
    cost_by_project = defaultdict(float)
    for r in calls:
        c = estimate_cost(r)
        cost_by_day[(r.get("ts") or "")[:10]] += c
        cost_by_project[r.get("project")] += c

    return {
        "total_calls": total,
        "top_tier_share": (top / total) if total else None,
        "top_tier_alert": bool(total and top / total > TOP_TIER_ALERT),
        "cache_hit_rate": (cache_hits / total) if total else None,
        "cache_alert": bool(total and cache_hits / total < CACHE_HIT_FLOOR),
        "escalation_rate": (escalated / total) if total else None,
        "escalation_mix": dict(Counter(
            r.get("escalation_trigger") for r in calls if r.get("escalated"))),
        "tier_mix": dict(Counter(r.get("tier") for r in calls)),
        "outcome_mix": dict(Counter(r.get("outcome") for r in calls)),
        "by_project": dict(Counter(r.get("project") for r in calls)),
        "est_cost_total_usd": round(sum(cost_by_day.values()), 4),
        "est_cost_by_day": {k: round(v, 4) for k, v in sorted(cost_by_day.items())},
        "est_cost_by_project": {k: round(v, 4) for k, v in cost_by_project.items()},
        # Models with no MODEL_RATES entry contribute $0 to the cost estimate;
        # surface them so a blank rate reads as "unpriced", not "free".
        "unpriced_models": dict(Counter(
            r.get("model") for r in calls
            if r.get("model") and r.get("model") not in MODEL_RATES)),
        "route_reasons": dict(Counter(r.get("route_reason") for r in calls)),
        "gate_kinds": dict(Counter(r.get("kind") for r in gates)),
        "gate_decisions": dict(Counter(r.get("decision") for r in gates)),
    }


def pct(x):
    """Format a 0-1 ratio as a percentage (public: reused by the demo/CLI)."""
    return "—" if x is None else f"{x * 100:.1f}%"


def render_html(signals):
    def rows(d):
        return "".join(
            f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
            for k, v in d.items()) or "<tr><td colspan=2>none</td></tr>"

    def badge(alert):
        return ('<span class="ok">within target</span>' if not alert
                else '<span class="alert">over target</span>')

    return f"""<!doctype html>
<meta charset="utf-8"><title>Eli OS — Telemetry Dashboard</title>
<style>
  body{{font:14px/1.5 -apple-system,Segoe UI,Inter,sans-serif;max-width:900px;
    margin:2rem auto;padding:0 1rem;color:#1a1a1f;background:#fafafa}}
  h1{{color:#7c3aed}} h2{{margin-top:2rem;border-bottom:1px solid #e5e5ea;padding-bottom:.3rem}}
  .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}}
  .kpi{{background:#fff;border:1px solid #e5e5ea;border-radius:.6rem;padding:1rem}}
  .kpi .v{{font-size:1.6rem;font-weight:700}} .kpi .l{{color:#6b7280;font-size:.8rem}}
  table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e5e5ea;border-radius:.4rem}}
  td{{padding:.4rem .7rem;border-bottom:1px solid #f0f0f3}}
  .ok{{color:#15803d}} .alert{{color:#b91c1c;font-weight:700}}
</style>
<h1>Eli OS — Telemetry Dashboard</h1>
<p>{signals['total_calls']} model call(s). Estimated spend
   <strong>${signals['est_cost_total_usd']:.4f}</strong>.</p>
<div class="kpis">
  <div class="kpi"><div class="v">{pct(signals['top_tier_share'])}</div>
    <div class="l">top-tier share {badge(signals['top_tier_alert'])}</div></div>
  <div class="kpi"><div class="v">{pct(signals['cache_hit_rate'])}</div>
    <div class="l">cache-hit rate {badge(signals['cache_alert'])}</div></div>
  <div class="kpi"><div class="v">{pct(signals['escalation_rate'])}</div>
    <div class="l">escalation rate</div></div>
  <div class="kpi"><div class="v">${signals['est_cost_total_usd']:.2f}</div>
    <div class="l">estimated spend</div></div>
</div>
<h2>Tier mix</h2><table>{rows(signals['tier_mix'])}</table>
<h2>Escalation triggers</h2><table>{rows(signals['escalation_mix'])}</table>
<h2>Outcomes</h2><table>{rows(signals['outcome_mix'])}</table>
<h2>Estimated cost by project</h2><table>{rows(signals['est_cost_by_project'])}</table>
<h2>Estimated cost by day</h2><table>{rows(signals['est_cost_by_day'])}</table>
<h2>Guardrail gate decisions</h2><table>{rows(signals['gate_decisions'])}</table>
<h2>Guardrail gate kinds</h2><table>{rows(signals['gate_kinds'])}</table>
"""


def main(argv):
    if len(argv) < 2:
        print("usage: dashboard.py <telemetry.jsonl> [out.html]")
        return 1
    signals = compute_signals(load_records(argv[1]))
    out = argv[2] if len(argv) > 2 else "eli_dashboard.html"
    Path(out).write_text(render_html(signals))
    print(f"wrote {out}  ({signals['total_calls']} calls, "
          f"top-tier {pct(signals['top_tier_share'])}, "
          f"est ${signals['est_cost_total_usd']:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

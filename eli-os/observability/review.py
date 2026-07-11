#!/usr/bin/env python3
"""Eli OS feedback review — Phase 6 (roadmap: eli-os/plans/roadmap.md).

The periodic review from telemetry_spec.md § Feedback loop: read the telemetry
signals and emit concrete, reviewable routing / prompt / budget / permission
change suggestions. It proposes; a human applies them as a versioned PR against
eli-os/ — nothing here auto-edits policy. Stdlib only.
"""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "memory"))
import memory  # noqa: E402

import dashboard  # noqa: E402


def generate_suggestions(records, policy_store=None):
    """Return a list of concrete change suggestions grounded in telemetry."""
    policy = policy_store or memory.PolicyStore()
    signals = dashboard.compute_signals(records)
    calls = [r for r in records if r.get("record") == "model_call"]
    gates = [r for r in records if r.get("record") == "gate"]
    suggestions = []
    target = policy.top_tier_share_target() or 0.10

    # 1. Top-tier share over target -> routing review, naming the driver.
    if signals["top_tier_share"] is not None and signals["top_tier_share"] > dashboard.TOP_TIER_ALERT:
        top_reasons = Counter(r.get("route_reason") for r in calls if r.get("tier") == "top")
        driver, n = (top_reasons.most_common(1) or [("unknown", 0)])[0]
        suggestions.append({
            "type": "routing", "severity": "high",
            "finding": f"top-tier share {signals['top_tier_share']*100:.1f}% "
                       f"exceeds the {dashboard.TOP_TIER_ALERT*100:.0f}% alert "
                       f"(target {target*100:.0f}%)",
            "suggested_change": f"review the rule/override behind '{driver}' in "
                                f"routing/model_tree.json — it drove {n} top-tier call(s); "
                                f"consider routing that task type to opus with escalation.",
            "evidence": {"route_reason": driver, "count": n},
        })

    # 2. Cache-hit rate below floor -> prompt-stability review.
    if signals["cache_hit_rate"] is not None and signals["cache_hit_rate"] < dashboard.CACHE_HIT_FLOOR:
        suggestions.append({
            "type": "prompt", "severity": "medium",
            "finding": f"cache-hit rate {signals['cache_hit_rate']*100:.1f}% "
                       f"is below the {dashboard.CACHE_HIT_FLOOR*100:.0f}% floor",
            "suggested_change": "audit prompt assembly for a silent invalidator "
                                "(volatile content in the stable prefix); verify prefixes "
                                "are byte-stable per cache_key_schema.md.",
            "evidence": {"cache_hit_rate": round(signals["cache_hit_rate"], 3)},
        })

    # 3. A dominant escalation trigger -> targeted routing/prompt fix.
    if signals["escalation_mix"]:
        trig, n = Counter(signals["escalation_mix"]).most_common(1)[0]
        suggestions.append({
            "type": "routing", "severity": "medium",
            "finding": f"escalations dominated by '{trig}' ({n} occurrence(s))",
            "suggested_change": f"if '{trig}' recurs on the same task type, lower that "
                                f"type's default tier or tighten its prompt so Opus "
                                f"converges without escalating.",
            "evidence": {"trigger": trig, "count": n},
        })

    # 4. Project over daily budget -> batch suggestion.
    for project, cost in signals["est_cost_by_project"].items():
        ceiling = policy.daily_ceiling(project)
        proj_tokens = sum((r.get("tokens", {}).get("in", 0) + r.get("tokens", {}).get("out", 0))
                          for r in calls if r.get("project") == project)
        if ceiling and proj_tokens > ceiling:
            suggestions.append({
                "type": "budget", "severity": "high",
                "finding": f"project '{project}' used {proj_tokens} tokens, over its "
                           f"{ceiling} daily ceiling",
                "suggested_change": f"move '{project}' bulk/non-interactive work to the "
                                    f"Batch API; defer non-essential calls.",
                "evidence": {"project": project, "tokens": proj_tokens, "ceiling": ceiling},
            })

    # 5. Repeated RBAC denials for a principal -> permission review.
    denials = Counter(r.get("principal") for r in gates
                      if r.get("kind") == "rbac_denial")
    for principal, n in denials.items():
        if n >= 3:
            suggestions.append({
                "type": "permission", "severity": "low",
                "finding": f"principal '{principal}' hit {n} RBAC denials",
                "suggested_change": f"review whether '{principal}' needs a broader "
                                    f"permission in the policy store, or whether the "
                                    f"denials indicate misrouted work.",
                "evidence": {"principal": principal, "denials": n},
            })

    return suggestions


def main(argv):
    if len(argv) < 2:
        print("usage: review.py <telemetry.jsonl>")
        return 1
    records = dashboard.load_records(argv[1])
    suggestions = generate_suggestions(records)
    print(json.dumps({"suggestion_count": len(suggestions),
                      "suggestions": suggestions}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

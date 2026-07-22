#!/usr/bin/env python3
"""Phase 6 acceptance tests (eli-os/plans/roadmap.md):
- the dashboard computes the watched signals and renders self-contained HTML
- the review produces at least one concrete routing/prompt suggestion from
  real telemetry
Offline: synthetic telemetry records; no network.
"""

import unittest

import dashboard
import review


def model_call(tier, model, project="eli_guardian", cache_hit=False,
               escalated=False, trigger=None, tokens=None, outcome="ok", ts="2026-07-11T00:00:00"):
    return {"record": "model_call", "ts": ts, "tier": tier, "model": model,
            "project": project, "cache_hit": cache_hit, "escalated": escalated,
            "escalation_trigger": trigger, "outcome": outcome,
            "route_reason": f"rule:{tier}",
            "tokens": tokens or {"in": 1000, "out": 500, "cached": 0}}


def gate(kind, decision="denied", principal="service_guardian"):
    return {"record": "gate", "ts": "2026-07-11T00:00:00", "principal": principal,
            "kind": kind, "action": "x", "reversibility": "n/a",
            "decision": decision, "result": "n/a"}


class SignalTests(unittest.TestCase):
    def test_top_tier_share_and_alert(self):
        recs = [model_call("top", "claude-fable-5") for _ in range(9)]
        recs.append(model_call("haiku", "claude-haiku-4-5"))
        s = dashboard.compute_signals(recs)
        self.assertAlmostEqual(s["top_tier_share"], 0.9)
        self.assertTrue(s["top_tier_alert"])

    def test_cache_hit_rate_and_alert(self):
        recs = [model_call("opus", "claude-opus-4-8", cache_hit=(i < 3)) for i in range(10)]
        s = dashboard.compute_signals(recs)
        self.assertAlmostEqual(s["cache_hit_rate"], 0.3)
        self.assertTrue(s["cache_alert"])  # 30% < 70% floor

    def test_estimated_cost_uses_rate_table(self):
        # 1000 in + 500 out on opus (5/25 per 1M) = 0.005 + 0.0125 = 0.0175
        s = dashboard.compute_signals([model_call("opus", "claude-opus-4-8")])
        self.assertAlmostEqual(s["est_cost_total_usd"], 0.0175, places=4)

    def test_cached_tokens_priced_lower(self):
        full = dashboard.estimate_cost(model_call("opus", "claude-opus-4-8",
                                                  tokens={"in": 1000, "out": 0, "cached": 0}))
        cached = dashboard.estimate_cost(model_call("opus", "claude-opus-4-8",
                                                    tokens={"in": 1000, "out": 0, "cached": 1000}))
        self.assertLess(cached, full)  # cache read ~0.1x

    def test_escalation_mix_counts_triggers(self):
        recs = [model_call("top", "claude-fable-5", escalated=True,
                           trigger="conflicting_outputs_across_runs") for _ in range(2)]
        s = dashboard.compute_signals(recs)
        self.assertEqual(s["escalation_mix"]["conflicting_outputs_across_runs"], 2)

    def test_gate_decisions_counted(self):
        s = dashboard.compute_signals([gate("rbac_denial", "denied"),
                                       gate("confirmation_pause", "paused")])
        self.assertEqual(s["gate_decisions"]["denied"], 1)
        self.assertEqual(s["gate_decisions"]["paused"], 1)


class HtmlTests(unittest.TestCase):
    def test_html_is_self_contained(self):
        s = dashboard.compute_signals([model_call("opus", "claude-opus-4-8")])
        out = dashboard.render_html(s)
        self.assertIn("<!doctype html>", out)
        self.assertIn("<style>", out)          # inline CSS, no external asset
        self.assertNotIn("http://", out)
        self.assertNotIn("https://", out)      # no external fetches
        self.assertIn("Eli OS", out)

    def test_html_escapes_values(self):
        recs = [dict(model_call("opus", "claude-opus-4-8"), route_reason="<script>x</script>")]
        out = dashboard.render_html(dashboard.compute_signals(recs))
        self.assertNotIn("<script>x</script>", out)


class ReviewTests(unittest.TestCase):
    def test_high_top_tier_share_yields_routing_suggestion(self):
        recs = [model_call("top", "claude-fable-5") for _ in range(9)]
        recs.append(model_call("haiku", "claude-haiku-4-5"))
        sugg = review.generate_suggestions(recs)
        self.assertTrue(sugg)  # at least one concrete suggestion
        routing = [s for s in sugg if s["type"] == "routing"]
        self.assertTrue(routing)
        self.assertIn("model_tree.json", routing[0]["suggested_change"])
        self.assertIn("count", routing[0]["evidence"])

    def test_low_cache_hit_yields_prompt_suggestion(self):
        recs = [model_call("opus", "claude-opus-4-8", cache_hit=False) for _ in range(10)]
        sugg = review.generate_suggestions(recs)
        self.assertTrue(any(s["type"] == "prompt" for s in sugg))

    def test_repeated_rbac_denials_yield_permission_suggestion(self):
        recs = [model_call("haiku", "claude-haiku-4-5")]
        recs += [gate("rbac_denial", "denied", "service_guardian") for _ in range(3)]
        sugg = review.generate_suggestions(recs)
        perm = [s for s in sugg if s["type"] == "permission"]
        self.assertTrue(perm)
        self.assertEqual(perm[0]["evidence"]["denials"], 3)

    def test_healthy_telemetry_yields_no_alarms(self):
        # Mostly cheap tiers, all cache hits -> no routing/prompt suggestions.
        recs = [model_call("haiku", "claude-haiku-4-5", cache_hit=True) for _ in range(20)]
        sugg = review.generate_suggestions(recs)
        self.assertFalse([s for s in sugg if s["type"] in ("routing", "prompt")])


if __name__ == "__main__":
    unittest.main(verbosity=2)

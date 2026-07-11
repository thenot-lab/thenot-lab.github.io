#!/usr/bin/env python3
"""Phase 1 acceptance tests (eli-os/plans/roadmap.md):
- a request with each task type routes to the tier the policy predicts
- every call writes a telemetry record in the telemetry_spec schema
Offline by design — no API key, no network (dry_run everywhere).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import gateway


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = gateway.load_policy()

    def test_every_project_override_routes_as_policy_predicts(self):
        tiers = set(self.policy["tiers"])
        for project, overrides in self.policy["project_overrides"].items():
            for task_type, value in overrides.items():
                expected = gateway._resolve_override(value)
                if expected["tier"] not in tiers:  # e.g. top_tier_access: escalation_only
                    continue
                decision = gateway.route({"project": project, "task_type": task_type}, self.policy)
                self.assertEqual(decision["tier"], expected["tier"],
                                 f"{project}/{task_type} routed to {decision['tier']}")
                self.assertEqual(decision["batch"], expected["batch"])
                self.assertEqual(decision["model"],
                                 self.policy["tiers"][expected["tier"]]["model"])
                self.assertIn("project_override", decision["route_reason"])

    def test_rule_routing_per_task_type(self):
        cases = {
            "architecture_decision": "top",
            "strategy": "top",
            "multi_step_plan": "opus",
            "deep_research": "opus",
            "doc_operation": "sonnet",
            "summarize": "sonnet",
            "chat": "haiku",
            "triage": "haiku",
        }
        for task_type, expected_tier in cases.items():
            decision = gateway.route({"task_type": task_type}, self.policy)
            self.assertEqual(decision["tier"], expected_tier,
                             f"{task_type} routed to {decision['tier']}")

    def test_risk_flag_forces_top_tier(self):
        decision = gateway.route(
            {"task_type": "chat", "risk_flags": ["high_impact_decision"]}, self.policy)
        self.assertEqual(decision["tier"], "top")
        self.assertIn("risk_flags", decision["route_reason"])

    def test_unmatched_task_type_hits_default_rule(self):
        decision = gateway.route({"task_type": "something_novel"}, self.policy)
        self.assertEqual(decision["tier"], "sonnet")
        self.assertEqual(decision["route_reason"], "rule:default")

    def test_classifier_infers_task_type_when_missing(self):
        decision = gateway.route({"prompt": "Please summarize this document"}, self.policy)
        self.assertEqual(decision["features"]["task_type"], "summarize")
        short = gateway.route({"prompt": "hi there"}, self.policy)
        self.assertEqual(short["features"]["task_type"], "chat")
        self.assertEqual(short["tier"], "haiku")


class EscalationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = gateway.load_policy()

    def test_triggers_use_canonical_names(self):
        fired = gateway.check_escalation(
            {"confidence": 0.4, "iterations": 3, "conflicting_runs": 2,
             "constraint_conflict": True}, self.policy)
        self.assertEqual(fired, ["self_reported_confidence",
                                 "iterations_without_convergence",
                                 "conflicting_outputs_across_runs",
                                 "constraint_conflict_detected"])

    def test_no_triggers_when_signals_healthy(self):
        fired = gateway.check_escalation(
            {"confidence": 0.9, "iterations": 1, "conflicting_runs": 0}, self.policy)
        self.assertEqual(fired, [])


class PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = gateway.load_policy()

    def _payload_for(self, task_type):
        decision = gateway.route({"task_type": task_type}, self.policy)
        return decision, gateway.build_payload(decision, {"prompt": "x", "system": "s"})

    def test_top_tier_gets_fallbacks_and_no_thinking_param(self):
        decision, payload = self._payload_for("architecture_decision")
        self.assertEqual(payload["fallbacks"], [{"model": "claude-opus-4-8"}])
        self.assertNotIn("thinking", payload)  # Fable 5: always on, param rejected

    def test_opus_gets_adaptive_thinking_and_effort(self):
        decision, payload = self._payload_for("multi_step_plan")
        self.assertEqual(payload["thinking"], {"type": "adaptive"})
        self.assertEqual(payload["output_config"], {"effort": "high"})

    def test_haiku_gets_no_thinking_or_effort(self):
        decision, payload = self._payload_for("chat")
        self.assertNotIn("thinking", payload)
        self.assertNotIn("output_config", payload)

    def test_system_prefix_carries_cache_control(self):
        _, payload = self._payload_for("chat")
        self.assertEqual(payload["system"][0]["cache_control"], {"type": "ephemeral"})


class TelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = gateway.load_policy()

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        self._orig = gateway.TELEMETRY_PATH
        gateway.TELEMETRY_PATH = Path(self.tmp.name)

    def tearDown(self):
        gateway.TELEMETRY_PATH = self._orig
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_every_call_writes_a_schema_shaped_record(self):
        gateway.handle({"project": "eli_guardian",
                        "task_type": "finding_triage_dedup",
                        "dry_run": True}, self.policy, live=False)
        lines = Path(self.tmp.name).read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        for field in ("ts", "record", "request_id", "project", "tier", "model",
                      "route_reason", "escalated", "escalation_trigger", "tokens",
                      "cache_hit", "batch", "latency_ms", "guardrail_flags", "outcome"):
            self.assertIn(field, rec, f"telemetry record missing {field}")
        self.assertEqual(rec["record"], "model_call")
        self.assertEqual(rec["tier"], "haiku")
        self.assertEqual(rec["outcome"], "ok")
        self.assertEqual(rec["tokens"], {"in": 0, "out": 0, "cached": 0})

    def test_top_tier_share_and_budget_alert(self):
        for _ in range(9):
            gateway.handle({"task_type": "architecture_decision", "dry_run": True},
                           self.policy, live=False)
        gateway.handle({"task_type": "chat", "dry_run": True}, self.policy, live=False)
        share = gateway.top_tier_share()
        self.assertAlmostEqual(share, 0.9)
        decision = gateway.route({"task_type": "architecture_decision"}, self.policy)
        self.assertTrue(any(a.startswith("budget_guard:top_tier_share") for a in decision["alerts"]),
                        f"expected budget alert, got {decision['alerts']}")

    def test_gate_record_shape(self):
        rec = gateway.gate_record("req_x", "admin", "rbac_denial",
                                  "deploy_hook:trigger", "denied", "irreversible")
        for field in ("ts", "record", "request_id", "principal", "kind", "action",
                      "reversibility", "decision", "result"):
            self.assertIn(field, rec)
        self.assertEqual(rec["record"], "gate")


if __name__ == "__main__":
    unittest.main(verbosity=2)

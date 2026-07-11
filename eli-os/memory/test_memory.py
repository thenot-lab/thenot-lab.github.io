#!/usr/bin/env python3
"""Phase 2 acceptance tests (eli-os/plans/roadmap.md):
- escalation handoff carries the FULL short-term context, not a summary
- a stable (project, workflow, version, role) yields an identical cache key /
  byte-identical prefix; bumping the workflow version changes the key
Offline: in-memory SQLite, deterministic hash embedding, real brain-stack files.
"""

import unittest

import memory
import prompt_assembly


class ShortTermTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory.connect(":memory:")
        self.st = memory.ShortTermStore(self.conn)

    def test_records_outputs_with_confidence(self):
        self.st.create_session("s", project="eli_guardian")
        self.st.append_output("s", "n3", "opus", "finding A", 0.55)
        ctx = self.st.get("s")
        self.assertEqual(len(ctx["intermediate_outputs"]), 1)
        self.assertEqual(ctx["intermediate_outputs"][0]["confidence"], 0.55)

    def test_missing_session_raises(self):
        with self.assertRaises(KeyError):
            self.st.append_message("nope", "user", "hi")


class LongTermTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory.connect(":memory:")
        self.lt = memory.LongTermStore(self.conn)

    def test_search_ranks_lexically_related_first(self):
        self.lt.write("eli_guardian", "decision", "auth uses parameterized queries",
                      "All auth.py database queries are parameterized.")
        self.lt.write("eli_guardian", "decision", "logging retention policy",
                      "Logs are retained for 30 days then rotated.")
        hits = self.lt.search("is auth.py vulnerable to sql injection via queries",
                              project="eli_guardian", k=2)
        self.assertEqual(hits[0]["title"], "auth uses parameterized queries")

    def test_project_filter(self):
        self.lt.write("eli_guardian", "decision", "g", "guardian note")
        self.lt.write("consulting", "decision", "c", "consulting note")
        hits = self.lt.search("note", project="consulting")
        self.assertTrue(all(h["project"] == "consulting" for h in hits))

    def test_write_back_supersedes_and_hides_old(self):
        old = self.lt.write("eli_guardian", "decision", "x", "old decision")
        self.lt.write("eli_guardian", "decision", "x", "new decision", supersedes=old)
        titles = [h["text"] for h in self.lt.search("decision", project="eli_guardian", k=5)]
        self.assertIn("new decision", titles)
        self.assertNotIn("old decision", titles)  # superseded hidden by default


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.ps = memory.PolicyStore()

    def test_force_top_tier_on_security_critical(self):
        matched = self.ps.force_top_tier({"output_is_security_critical": True})
        self.assertIn("output_is_security_critical", matched)

    def test_no_force_when_routine(self):
        self.assertEqual(self.ps.force_top_tier({"decision_is_high_impact": False}), [])

    def test_budget_and_target_present(self):
        self.assertEqual(self.ps.daily_ceiling("eli_guardian"), 2000000)
        self.assertEqual(self.ps.top_tier_share_target(), 0.10)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory.connect(":memory:")
        self.st = memory.ShortTermStore(self.conn)
        self.lt = memory.LongTermStore(self.conn)

    def test_handoff_carries_full_trace_not_a_summary(self):
        self.st.create_session("s", project="eli_guardian", cache_key="k1")
        # Two conflicting low-confidence outputs — the contradiction is the signal.
        self.st.append_output("s", "n3a", "opus", "SQLi likely in auth.py:42", 0.55)
        self.st.append_output("s", "n3b", "opus", "false positive, parameterized", 0.50)
        self.lt.write("eli_guardian", "decision", "auth parameterized",
                      "auth.py queries are parameterized")
        h = memory.assemble_handoff("s", self.st, self.lt,
                                    "conflicting_outputs_across_runs")
        # Full trace: every output preserved, with confidence — not condensed.
        self.assertFalse(h["is_summary"])
        outs = h["short_term_context"]["intermediate_outputs"]
        self.assertEqual(len(outs), 2)
        self.assertEqual({o["confidence"] for o in outs}, {0.55, 0.50})
        self.assertEqual(h["cache_key"], "k1")
        self.assertEqual(h["escalation_reason"], "conflicting_outputs_across_runs")
        self.assertTrue(h["relevant_memory"])  # prior decision retrieved


class PromptAssemblyTests(unittest.TestCase):
    def test_stable_prefix_and_key_are_deterministic(self):
        a1 = prompt_assembly.assemble("net_sec_hardening", "reasoner",
                                      "goal A", "plan", ["c1"], "ctx A")
        a2 = prompt_assembly.assemble("net_sec_hardening", "reasoner",
                                      "goal B", "analysis", ["c2"], "ctx B")
        # Different variable suffixes, identical stable prefix + cache key.
        self.assertEqual(a1["cache_key"], a2["cache_key"])
        self.assertEqual(a1["stable_prefix"], a2["stable_prefix"])
        self.assertNotEqual(a1["variable_suffix"], a2["variable_suffix"])

    def test_key_encodes_project_workflow_version_role(self):
        a = prompt_assembly.assemble("net_sec_hardening", "reasoner",
                                     "g", "plan", [], "")
        self.assertEqual(
            a["cache_key"],
            f"project:dominion|workflow:net_sec_hardening|version:{a['version']}|role:reasoner")

    def test_different_role_changes_key_but_reuses_body(self):
        a = prompt_assembly.assemble("net_sec_hardening", "reasoner", "g", "plan", [], "")
        b = prompt_assembly.assemble("net_sec_hardening", "auditor", "g", "plan", [], "")
        self.assertNotEqual(a["cache_key"], b["cache_key"])
        # The pattern/workflow body is shared; only the SYSTEM role line differs.
        self.assertIn("net_sec_hardening", a["stable_prefix"])
        self.assertIn("net_sec_hardening", b["stable_prefix"])

    def test_ui_workflow_version_is_2(self):
        a = prompt_assembly.assemble("ui_surface_design", "architect", "g", "plan", [], "")
        self.assertEqual(a["version"], "2.0")
        self.assertIn("version:2.0", a["cache_key"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

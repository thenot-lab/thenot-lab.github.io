#!/usr/bin/env python3
"""Phase 3 acceptance tests (eli-os/plans/roadmap.md):
- the Guardian worked example runs end to end
- the top-tier node (n4) is skipped when its condition is unmet, runs when met,
  and n5 proceeds either way (skipped satisfies the dependency)
- retry policy: idempotent retries, action-bearing needs a key, irreversible
  never auto-retries
"""

import unittest

import task_graph
from task_graph import Node, TaskGraph, guardian_graph


def stub(name, conf=0.9):
    return lambda r: {"output": f"{name} ok", "confidence": conf}


def base_execs():
    return {"n1": stub("n1"), "n2": stub("n2"), "n3": stub("n3", 0.9),
            "n4": stub("n4"), "n5": stub("n5")}


class GuardianExampleTests(unittest.TestCase):
    def _run(self, n3_conf):
        execs = dict(base_execs(), n3=stub("n3", n3_conf))
        g = guardian_graph(execs, escalation_condition=lambda r: r["n3"]["confidence"] < 0.6)
        return g.execute()

    def test_confident_skips_top_tier_and_report_still_runs(self):
        agg = self._run(0.9)
        self.assertEqual(agg["statuses"]["n4"], "skipped")
        self.assertEqual(agg["statuses"]["n5"], "done")  # skipped dep satisfied
        self.assertNotIn("n4", agg["results"])           # no top-tier result

    def test_contested_runs_top_tier(self):
        agg = self._run(0.4)
        self.assertEqual(agg["statuses"]["n4"], "done")
        self.assertEqual(agg["statuses"]["n5"], "done")
        self.assertIn("n4", agg["results"])

    def test_all_five_nodes_reach_terminal(self):
        agg = self._run(0.9)
        self.assertTrue(all(s in task_graph.TERMINAL for s in agg["statuses"].values()))
        # Report node ran last (depends on the most).
        order = [nid for nid, st in agg["log"] if st == "done"]
        self.assertEqual(order[-1], "n5")


class RetryPolicyTests(unittest.TestCase):
    def _flaky(self, fail_times):
        state = {"calls": 0}

        def run(results):
            state["calls"] += 1
            if state["calls"] <= fail_times:
                raise RuntimeError("transient")
            return {"output": "ok"}
        return run, state

    def test_idempotent_node_retries(self):
        run, state = self._flaky(2)
        g = TaskGraph([Node("a", run, idempotent=True, max_retries=2)])
        agg = g.execute()
        self.assertEqual(agg["statuses"]["a"], "done")
        self.assertEqual(state["calls"], 3)  # 1 + 2 retries

    def test_action_node_without_key_does_not_retry(self):
        run, state = self._flaky(1)
        g = TaskGraph([Node("a", run, idempotent=False)])
        agg = g.execute()
        self.assertEqual(agg["statuses"]["a"], "failed")
        self.assertEqual(state["calls"], 1)  # no auto-retry

    def test_action_node_with_key_retries(self):
        run, state = self._flaky(1)
        g = TaskGraph([Node("a", run, idempotent=False, idempotency_key="k", max_retries=2)])
        agg = g.execute()
        self.assertEqual(agg["statuses"]["a"], "done")
        self.assertEqual(state["calls"], 2)

    def test_irreversible_node_never_auto_retries(self):
        run, state = self._flaky(1)
        g = TaskGraph([Node("a", run, irreversible=True, idempotency_key="k", max_retries=5)])
        agg = g.execute()
        self.assertEqual(agg["statuses"]["a"], "failed")
        self.assertEqual(state["calls"], 1)  # irreversible overrides everything


class DependencyTests(unittest.TestCase):
    def test_failed_dependency_blocks_dependent(self):
        def boom(results):
            raise RuntimeError("x")
        g = TaskGraph([
            Node("a", boom, idempotent=True, max_retries=0),
            Node("b", stub("b"), depends_on=["a"]),
        ])
        agg = g.execute()
        self.assertEqual(agg["statuses"]["a"], "failed")
        self.assertEqual(agg["statuses"]["b"], "blocked")  # surfaced, not silently dropped

    def test_independent_nodes_both_run(self):
        g = TaskGraph([Node("a", stub("a")), Node("b", stub("b"))])
        agg = g.execute()
        self.assertEqual(agg["statuses"], {"a": "done", "b": "done"})

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            TaskGraph([Node("a", stub("a")), Node("a", stub("a"))])


class ReviewHookTests(unittest.TestCase):
    def test_review_fn_runs_on_aggregate(self):
        seen = {}

        def review(agg):
            seen["n"] = len(agg["results"])
            return {"coherent": True}
        g = TaskGraph([Node("a", stub("a"))], review_fn=review)
        agg = g.execute()
        self.assertEqual(agg["review"], {"coherent": True})
        self.assertEqual(seen["n"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

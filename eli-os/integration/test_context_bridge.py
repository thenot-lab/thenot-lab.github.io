#!/usr/bin/env python3
"""Tests for the context bridge — the on-device Connect (Data) spine.

Stdlib unittest, temp-file SQLite, no network, no API key (mirrors the rest
of eli-os). Run: python3 eli-os/integration/test_context_bridge.py
"""
import json
import os
import tempfile
import unittest

import context_bridge as cb


class ContextStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = cb.ContextStore(self.tmp.name)
        self.tools = cb.make_tools(self.store)

    def tearDown(self):
        os.unlink(self.tmp.name)

    # -- ingest + retrieval ---------------------------------------------------
    def test_ingest_stores_event(self):
        r = self.store.ingest({"type": "notification",
                               "payload": {"package": "com.slack", "title": "hi"}})
        self.assertTrue(r["stored"])
        self.assertEqual(r["id"], 1)
        recent = self.store.recent("notification", 10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["payload"]["package"], "com.slack")

    def test_unknown_type_still_stored(self):
        # A new capture surface must need no change here.
        r = self.store.ingest({"type": "heart_rate", "payload": {"bpm": 72}})
        self.assertTrue(r["stored"])
        self.assertEqual(len(self.store.recent("heart_rate", 5)), 1)

    def test_recent_is_newest_first(self):
        for i in range(3):
            self.store.ingest({"type": "sms", "ts": f"2026-07-23T10:0{i}:00Z",
                               "payload": {"sender": f"P{i}", "body": f"m{i}"}})
        rows = self.store.recent("sms", 10)
        self.assertEqual(rows[0]["payload"]["sender"], "P2")

    # -- inferenced memory (honest, deterministic) ----------------------------
    def test_usage_snapshot_infers_most_used_app(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.foo:600000:1|com.bar:100:2"}})
        facts = {m["key"]: m["value"] for m in self.store.recall()}
        self.assertEqual(facts.get("most_used_app"), "com.foo")

    def test_remember_supersedes(self):
        self.store.remember("routine", "k", "v1", 0.5, "s")
        self.store.remember("routine", "k", "v2", 0.9, "s")
        vals = [m["value"] for m in self.store.recall("k")]
        self.assertEqual(vals, ["v2"])  # only the newest, superseded hidden

    def test_notification_counter_increments(self):
        for _ in range(3):
            self.store.ingest({"type": "notification",
                               "payload": {"package": "com.x"}})
        facts = {m["key"]: m["value"] for m in self.store.recall("notifs_from")}
        self.assertEqual(facts.get("notifs_from:com.x"), "3")

    # -- aggregation ----------------------------------------------------------
    def test_usage_summary_aggregates(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.a:300000:1|com.b:60000:2"}})
        summ = self.store.usage_summary()
        self.assertEqual(summ[0]["package"], "com.a")
        self.assertEqual(summ[0]["ms"], 300000)

    def test_search_context_matches_payload(self):
        self.store.ingest({"type": "share", "payload": {"body": "meeting at noon"}})
        self.store.ingest({"type": "share", "payload": {"body": "unrelated"}})
        hits = self.store.search("meeting", 10)
        self.assertEqual(len(hits), 1)

    def test_digest_is_grounded_when_empty(self):
        self.assertIn("No device context", self.store.digest())

    def test_digest_includes_usage(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.z:600000:1"}})
        self.assertIn("com.z", self.store.digest())

    # -- tool contract (must match tool_router: {tier,rc,out}) ----------------
    def test_tools_return_router_contract(self):
        self.store.ingest({"type": "notification", "payload": {"package": "com.q"}})
        for name, fn in self.tools.items():
            res = fn({"query": "com"})
            self.assertIn("tier", res, name)
            self.assertIn("rc", res, name)
            self.assertIn("out", res, name)
            self.assertEqual(res["tier"], "READ", name)

    def test_search_tool_requires_query(self):
        res = self.tools["search_context"]({})
        self.assertEqual(res["rc"], 2)

    def test_context_digest_tool(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.w:600000:1"}})
        res = self.tools["context_digest"]({})
        self.assertEqual(res["rc"], 0)
        self.assertIn("com.w", res["out"])

    # -- retention ------------------------------------------------------------
    def test_prune_removes_old(self):
        self.store.ingest({"type": "sms", "ts": "2000-01-01T00:00:00Z",
                           "payload": {"body": "old"}})
        self.store.ingest({"type": "sms", "payload": {"body": "new"}})
        removed = self.store.prune(retain_days=1)
        self.assertGreaterEqual(removed, 1)
        self.assertEqual(len(self.store.recent("sms", 10)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

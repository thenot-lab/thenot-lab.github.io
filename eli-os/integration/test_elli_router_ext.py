#!/usr/bin/env python3
"""Tests for the router extension — the context→Elli merge layer."""
import os
import tempfile
import unittest

import context_bridge as cb
import elli_router_ext as ext


# A minimal stand-in for tool_router's surface, so these tests don't need the
# private eli repo present. Built fresh per test (fresh_router) because
# patch_tool_router rebinds TOOLS/TOOL_SPEC in place — a shared class would
# leak context tools into later tests and trip the collision guard.
def fresh_router():
    class FakeRouter:
        TOOLS = {"device_info": lambda a: {"tier": "READ", "rc": 0, "out": "model=KEY2"}}
        TOOL_SPEC = (
            "You are Elli.\n"
            "  device_info{}                       -> model/os/battery/mem\n"
            "After a tool runs you receive RESULT.\n"
        )
    return FakeRouter


class RouterExtTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = cb.ContextStore(self.tmp.name)
        self.router = fresh_router()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_register_adds_context_tools(self):
        tools, spec = ext.register_context_tools(
            self.router.TOOLS, self.router.TOOL_SPEC, self.store)
        self.assertIn("context_digest", tools)
        self.assertIn("device_info", tools)          # original preserved
        self.assertIn("context_digest", spec)         # spec advertises it
        self.assertIn("After a tool runs", spec)      # marker retained

    def test_register_is_non_destructive(self):
        before = dict(self.router.TOOLS)
        ext.register_context_tools(self.router.TOOLS, self.router.TOOL_SPEC, self.store)
        self.assertEqual(self.router.TOOLS, before)    # caller's dict untouched

    def test_name_collision_raises(self):
        collide = {"context_digest": lambda a: {}}
        with self.assertRaises(ValueError):
            ext.register_context_tools(collide, self.router.TOOL_SPEC, self.store)

    def test_context_tool_actually_runs(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.app:600000:1"}})
        tools, _ = ext.register_context_tools(
            self.router.TOOLS, self.router.TOOL_SPEC, self.store)
        res = tools["context_digest"]({})
        self.assertIn("com.app", res["out"])

    def test_ground_messages_prepends_context(self):
        self.store.ingest({"type": "usage_snapshot",
                           "payload": {"top_apps": "com.app:600000:1"}})
        msgs = ext.ground_messages([{"role": "user", "content": "hi"}], self.store)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("com.app", msgs[0]["content"])
        self.assertEqual(msgs[1]["content"], "hi")    # original preserved, order kept

    def test_ground_messages_grounded_when_empty(self):
        msgs = ext.ground_messages([{"role": "user", "content": "hi"}], self.store)
        self.assertIn("No device context", msgs[0]["content"])

    def test_patch_tool_router_in_place(self):
        ext.patch_tool_router(self.router, self.store)
        self.assertIn("context_digest", self.router.TOOLS)
        self.assertIn("recall", self.router.TOOLS)


if __name__ == "__main__":
    unittest.main(verbosity=2)

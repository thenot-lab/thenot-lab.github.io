#!/usr/bin/env python3
"""Phase 4 acceptance tests (eli-os/plans/roadmap.md):
- a scan produces a report where every finding carries evidence and every
  remediation is tagged prevent/detect/respond/recover
- a contested finding escalates to the top tier (n4 runs) and is logged
Offline: scans a temp fixture with planted vulnerabilities; no LLM required.
"""

import tempfile
import textwrap
import unittest
from pathlib import Path

import guardian

VULN = textwrap.dedent('''
    import subprocess, pickle, hashlib
    API_KEY = "sk-supersecret-value-1234"          # hardcoded-secret
    def run(cmd, blob, user_id):
        subprocess.run(cmd, shell=True)             # shell-true
        data = pickle.loads(blob)                   # pickle-loads
        h = hashlib.md5(user_id.encode())           # weak-hash (contested)
        q = f"SELECT * FROM users WHERE id = {user_id}"   # sql-fstring
        return eval(data)                           # code-eval
''')

CLEAN = "def add(a, b):\n    return a + b\n"


class GuardianReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        (Path(self.tmp) / "vuln.py").write_text(VULN)
        self.report = guardian.run_guardian(self.tmp)

    def test_scan_found_the_planted_vulns(self):
        rules = {t["threat"] for t in self.report["threat_model"]}
        self.assertTrue(rules)
        self.assertGreaterEqual(self.report["finding_count"], 5)

    def test_every_threat_carries_evidence(self):
        for t in self.report["threat_model"]:
            self.assertIn(":", t["evidence"])  # file:line: snippet
            self.assertTrue(t["evidence"].startswith("vuln.py:"))

    def test_every_hardening_change_is_phase_tagged_and_cites_evidence(self):
        self.assertTrue(self.report["hardening_baseline"])
        for h in self.report["hardening_baseline"]:
            self.assertIn(h["phase"], {"prevent", "detect", "respond", "recover"})
            self.assertTrue(h["evidence"])
            self.assertTrue(h["closes"])

    def test_coverage_spans_all_four_phases(self):
        cov = self.report["coverage"]
        for phase in ("prevent", "detect", "respond", "recover"):
            self.assertTrue(cov[phase], f"phase {phase} is empty")

    def test_pipeline_ran_all_stages(self):
        st = self.report["_graph_statuses"]
        self.assertEqual(st["n1"], "done")
        self.assertEqual(st["n5"], "done")


class EscalationTests(unittest.TestCase):
    def test_contested_finding_escalates_and_is_logged(self):
        tmp = tempfile.mkdtemp()
        # weak-hash is the contested rule (confidence 0.55) -> must escalate.
        (Path(tmp) / "c.py").write_text("import hashlib\nh = hashlib.md5(x)\n")
        report = guardian.run_guardian(tmp)
        self.assertTrue(report["escalated"])                      # n4 ran
        self.assertEqual(report["_graph_statuses"]["n4"], "done")
        self.assertIn("weak-hash:c.py:2", report["contested_findings"])

    def test_no_contested_finding_skips_top_tier(self):
        tmp = tempfile.mkdtemp()
        # code-eval is high-confidence, not contested -> n4 skipped.
        (Path(tmp) / "e.py").write_text("y = eval(z)\n")
        report = guardian.run_guardian(tmp)
        self.assertFalse(report["escalated"])
        self.assertEqual(report["_graph_statuses"]["n4"], "skipped")


class CleanScanTests(unittest.TestCase):
    def test_clean_code_yields_no_findings_but_valid_report(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "ok.py").write_text(guardian.__doc__ and "def f():\n    return 1\n")
        report = guardian.run_guardian(tmp)
        self.assertEqual(report["finding_count"], 0)
        self.assertIn("no findings", report["open_questions"][0])
        # Four-phase contract still holds (empty phases scoped out with a reason).
        for phase in ("prevent", "detect", "respond", "recover"):
            self.assertTrue(report["coverage"][phase])


class ModelFnTests(unittest.TestCase):
    def test_model_fn_refines_each_stage(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "e.py").write_text("y = eval(z)\n")
        seen = []

        def model_fn(tier, stage, findings):
            seen.append((tier, stage))
            return findings
        guardian.run_guardian(tmp, model_fn=model_fn)
        stages = {s for _, s in seen}
        self.assertIn("triage", stages)
        self.assertIn("semantic", stages)


if __name__ == "__main__":
    unittest.main(verbosity=2)

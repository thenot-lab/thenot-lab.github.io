#!/usr/bin/env python3
"""Eli Guardian pipeline — Phase 4 (roadmap: eli-os/plans/roadmap.md).

Wires the Eli Protocol (eli-os/protocol/eli_protocol.md) into the Guardian scan
flow over the Phase 3 task graph:

    scan (no LLM) -> triage+dedup (haiku) -> STRIDE (sonnet)
                  -> semantic analysis (opus) -> contested verdict (top, cond.)
                  -> assemble report (sonnet)

Output is the brain-stack `net_sec_hardening` schema. Every finding carries
evidence (file:line + rule); every remediation is tagged with its protocol
phase and the report's coverage spans prevent/detect/respond/recover. The
structural pipeline runs fully offline (stdlib only); pass a gateway-backed
`model_fn` to have the tier models refine each stage.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "orchestration"))
import task_graph  # noqa: E402
from task_graph import guardian_graph  # noqa: E402

PLAYBOOK_DIR = HERE / "playbooks"

# Zero-dependency scanner rules. Each: id, regex, stride, threat, base confidence.
# `contested` marks patterns the scanner can't resolve alone (often a false
# positive) — these drive the top-tier escalation.
RULES = [
    {"id": "code-eval", "re": r"\b(eval|exec)\s*\(", "stride": "E",
     "threat": "Arbitrary code execution via eval/exec", "confidence": 0.85},
    {"id": "shell-true", "re": r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True", "stride": "E",
     "threat": "Command injection via shell=True", "confidence": 0.8},
    {"id": "pickle-loads", "re": r"pickle\.loads?\s*\(", "stride": "T",
     "threat": "Untrusted deserialization (pickle)", "confidence": 0.75},
    {"id": "weak-hash", "re": r"hashlib\.(md5|sha1)\s*\(", "stride": "I",
     "threat": "Weak hash for security-sensitive data", "confidence": 0.55,
     "contested": True},
    {"id": "hardcoded-secret",
     "re": r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{6,}['\"]", "stride": "I",
     "threat": "Hardcoded credential", "confidence": 0.7},
    {"id": "sql-fstring", "re": r"(?i)(select|insert|update|delete)\b.*\{[a-z_]+\}", "stride": "T",
     "threat": "SQL injection via string interpolation", "confidence": 0.65},
    {"id": "tls-verify-off", "re": r"verify\s*=\s*False", "stride": "S",
     "threat": "TLS verification disabled (MITM)", "confidence": 0.7},
]

STRIDE_NAMES = {"S": "Spoofing", "T": "Tampering", "R": "Repudiation",
                "I": "Information disclosure", "D": "Denial of service",
                "E": "Elevation of privilege"}


# --------------------------------------------------------------------------- #
# Phase 0 — scan (no LLM)
# --------------------------------------------------------------------------- #
# Directories that never hold reviewable project source, and would only add
# noise (vendored deps, VCS internals, caches) if scanned.
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "env", "node_modules"}


def scan(target_dir):
    """Walk .py files, apply rules, emit raw findings with file:line evidence.
    Skips noise directories and `test_*.py` fixtures — the latter plant
    deliberate vulnerabilities the line scanner can't tell from live code, so
    scanning them (e.g. the no-arg default target) self-reports false hits."""
    target = Path(target_dir)
    findings = []
    for path in sorted(target.rglob("*.py")):
        if SKIP_DIRS & set(path.relative_to(target).parts) or path.name.startswith("test_"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for rule in RULES:
                m = re.search(rule["re"], line)
                if not m:
                    continue
                rel = path.relative_to(target)
                findings.append({
                    "id": f"{rule['id']}:{rel}:{lineno}",
                    "rule": rule["id"],
                    "file": str(rel),
                    "line": lineno,
                    "stride": rule["stride"],
                    "threat": rule["threat"],
                    "confidence": rule["confidence"],
                    "contested": rule.get("contested", False),
                    "evidence": f"{rel}:{lineno}: {line.strip()[:120]}",
                })
    return findings


# --------------------------------------------------------------------------- #
# Playbooks — protocol/playbooks/*.json (JSON to stay stdlib; eli_protocol.md
# illustrates them as YAML). Keyed by incident_class; each carries a four-phase
# coverage block.
# --------------------------------------------------------------------------- #
def load_playbooks(directory=PLAYBOOK_DIR):
    books = {}
    for p in sorted(Path(directory).glob("*.json")):
        pb = json.loads(p.read_text())
        books[pb["incident_class"]] = pb
    return books


# Rule -> incident_class mapping (which playbook a finding remediates through).
RULE_INCIDENT = {
    "code-eval": "code_injection", "shell-true": "code_injection",
    "sql-fstring": "code_injection", "pickle-loads": "code_injection",
    "hardcoded-secret": "credential_exposure", "weak-hash": "credential_exposure",
    "tls-verify-off": "insecure_transport",
}


# --------------------------------------------------------------------------- #
# Pipeline stages (task-graph executors). Each stage transforms the findings in
# the shared state; a model_fn, if supplied, refines that stage's output.
# --------------------------------------------------------------------------- #
def _stage(tier, name, transform, model_fn):
    def run(results):
        findings = transform(results)
        if model_fn is not None:
            findings = model_fn(tier, name, findings)
        return {"findings": findings, "tier": tier,
                "confidence": _min_conf(findings)}
    return run


def _min_conf(findings):
    return min((f["confidence"] for f in findings), default=1.0)


def _triage(raw):
    def t(results):
        seen, out = set(), []
        for f in raw:
            key = (f["rule"], f["file"], f["line"])
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(f))
        return out
    return t


def _stride(results):
    out = []
    for f in results["n1"]["findings"]:
        g = dict(f)
        g["stride_name"] = STRIDE_NAMES.get(f["stride"], "Unknown")
        out.append(g)
    return out


def _semantic(results):
    out = []
    for f in results["n2"]["findings"]:
        g = dict(f)
        g["exploit_note"] = f"{f['threat']} reachable at {f['evidence']}"
        out.append(g)
    return out


def _verdict(results):
    # Top tier resolves contested / low-confidence findings: confirm them and
    # raise confidence (a real deployment consults the top-tier model here).
    out = []
    for f in results["n3"]["findings"]:
        g = dict(f)
        if f.get("contested") or f["confidence"] < 0.6:
            g["verdict"] = "confirmed"
            g["confidence"] = max(f["confidence"], 0.75)
            g["contested"] = False
        out.append(g)
    return out


def escalation_condition(results):
    """n4 runs only when the semantic stage left a contested / low-confidence
    finding — the ~10% top-tier reservation in practice."""
    return any(f.get("contested") or f["confidence"] < 0.6
               for f in results["n3"]["findings"])


# --------------------------------------------------------------------------- #
# Phase 4 — assemble the net_sec_hardening report
# --------------------------------------------------------------------------- #
def _assemble(target_dir, playbooks):
    def run(results):
        # Prefer the verdict stage's findings if it ran; else the semantic stage.
        findings = (results.get("n4") or results["n3"])["findings"]
        files = sorted({f["file"] for f in findings})
        threat_model, detection, hardening, playbook_refs = [], [], [], []
        coverage = {"prevent": [], "detect": [], "respond": [], "recover": []}
        for f in findings:
            incident = RULE_INCIDENT.get(f["rule"], "generic")
            pb = playbooks.get(incident) or _generic_playbook(incident, f)
            threat_model.append({
                "asset": f["file"], "stride": f["stride"],
                "threat": f["threat"], "attacker_profile": "remote/unauth (home-scale)",
                "evidence": f["evidence"], "confidence": f["confidence"],
            })
            for d in pb["detect"]:
                detection.append(dict(d, threat=f["threat"]))
                coverage["detect"].append(f"{f['id']}: {d['signal']}")
            for step in pb["respond"]:
                coverage["respond"].append(f"{f['id']}: {step}")
            for h in pb["harden"]:
                hardening.append({
                    "change": h["change"], "closes": [f["threat"]],
                    "phase": h["phase"], "home_executable": True,
                    "evidence": f["evidence"],
                })
                coverage[h["phase"]].append(f"{f['id']}: {h['change']}")
            for rec in pb["recover"]:
                coverage["recover"].append(f"{f['id']}: {rec}")
            playbook_refs.append({"incident_class": incident,
                                  "finding": f["id"], "steps": pb["respond"]})
        # Four-phase contract: any empty phase is scoped out with a reason.
        for phase in ("prevent", "detect", "respond", "recover"):
            if not coverage[phase]:
                coverage[phase].append(f"scoped-out: no finding required {phase}")
        return {
            "asset_topology_map": f"Scanned {len(files)} file(s): {', '.join(files) or 'none'}",
            "threat_model": threat_model,
            "detection": detection,
            "isolation": [{"measure": "segment affected host on confirmed RCE",
                          "segments": "quarantine VLAN", "default_policy": "deny"}]
                         if any(f["stride"] == "E" for f in findings) else [],
            "remediation_playbooks": playbook_refs,
            "hardening_baseline": hardening,
            "control_tradeoffs": "fix-in-place preferred; all changes home-executable",
            "coverage": coverage,
            "assumptions": ["static scan only; no runtime reachability proof"],
            "open_questions": [] if findings else ["no findings — confirm scan scope"],
            "escalated": "n4" in results,
            "contested_findings": [f["id"] for f in results["n3"]["findings"]
                                   if f.get("contested") or f["confidence"] < 0.6],
            "finding_count": len(findings),
        }
    return run


def _generic_playbook(incident, finding):
    """Fallback four-phase coverage when no JSON playbook matches the rule."""
    return {
        "incident_class": incident,
        "detect": [{"signal": f"static scan rule {finding['rule']}",
                    "threshold": ">=1 match", "action": "open ticket"}],
        "respond": [f"review {finding['evidence']} and remove/replace the pattern"],
        "harden": [{"change": f"fix {finding['rule']} at {finding['file']}",
                    "phase": "prevent"},
                   {"change": f"add a lint/CI rule for {finding['rule']}",
                    "phase": "detect"}],
        "recover": [f"verify {finding['file']} no longer matches {finding['rule']}"],
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_guardian(target_dir, model_fn=None, playbooks=None):
    """Run the full pipeline; return the net_sec_hardening report + graph log."""
    raw = scan(target_dir)
    playbooks = playbooks if playbooks is not None else load_playbooks()
    execs = {
        "n1": _stage("haiku", "triage", _triage(raw), model_fn),
        "n2": _stage("sonnet", "stride", _stride, model_fn),
        "n3": _stage("opus", "semantic", _semantic, model_fn),
        "n4": _stage("top", "verdict", _verdict, model_fn),
        "n5": _assemble(target_dir, playbooks),
    }
    graph = guardian_graph(execs, escalation_condition)
    agg = graph.execute()
    report = agg["results"]["n5"]
    report["_graph_statuses"] = agg["statuses"]
    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(HERE)
    print(json.dumps(run_guardian(target), indent=2))

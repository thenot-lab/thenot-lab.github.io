#!/usr/bin/env python3
"""Prompt assembly + cache keying — Phase 2 (roadmap: eli-os/plans/roadmap.md).

Assembles the cacheable stable prefix from the brain-stack files in the order
prompts/prompt_reasoner.md prescribes (global -> project -> patterns ->
workflow), then the variable suffix, and computes the deterministic cache key
from brain-stack/cache/cache_key_schema.md.

The whole point: for a given (project, workflow, version, role) the prefix is
byte-identical across calls, so the prompt cache actually hits. The offline
acceptance proxy is exactly that — same inputs -> identical prefix -> identical
key; bump the workflow version and the key changes.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAIN = HERE.parent.parent / "brain-stack"

# Pattern files loaded whole (a named skeleton lives inside its pattern file).
PATTERN_FILES = [
    "patterns/reasoning_skeletons.md",
    "patterns/decomposition_trees.md",
    "patterns/tradeoff_patterns.md",
    "patterns/evidence_rules.md",
]


def load_index(brain=BRAIN):
    return json.loads((Path(brain) / "workflows" / "workflow_index.json").read_text())


def _read(brain, rel):
    return (Path(brain) / rel).read_text()


def cache_key(project, workflow_id, version, role):
    """cache_key_schema.md formula — role is in the key (bound in the SYSTEM
    block, part of the prefix); mode is the variable suffix and is excluded."""
    return "|".join([
        f"project:{project}",
        f"workflow:{workflow_id}",
        f"version:{version}",
        f"role:{role}",
    ])


def assemble(workflow_id, role, goal, mode, constraints, context,
             brain=BRAIN, index=None):
    """Return {cache_key, stable_prefix, variable_suffix, workflow}.

    stable_prefix is the cacheable bytes; variable_suffix carries the per-call
    goal/mode/constraints/context. Assembly order is fixed so the prefix is
    stable for a given (project, workflow, version, role).
    """
    index = index or load_index(brain)
    wf = index["workflows"][workflow_id]
    project = wf["project"]
    version = _workflow_version(brain, wf["spec"])

    parts = [
        _read(brain, "CLAUDE.global.md"),
        _read(brain, f"projects/CLAUDE.project.{project}.md"),
    ]
    parts += [_read(brain, p) for p in PATTERN_FILES]
    parts.append(_read(brain, wf["spec"]))
    system_block = (
        f"You are the {role} for project {project}.\n"
        f"Follow workflow {workflow_id} v{version}.\n"
        f"Apply skeleton {wf['skeleton']} and decomposition {wf['decomposition']}.\n"
        "Obey the evidence rules and check the failure modes before emitting output.\n"
        "Emit output strictly in the workflow's output schema."
    )
    stable_prefix = system_block + "\n\n===\n\n" + "\n\n===\n\n".join(parts)

    constraint_lines = "\n".join(f"- {c}" for c in (constraints or []))
    variable_suffix = (
        f"Goal: {goal}\n"
        f"Mode: {mode}\n"
        f"Constraints:\n{constraint_lines}\n"
        f"Context:\n{context or ''}"
    )
    return {
        "cache_key": cache_key(project, workflow_id, version, role),
        "stable_prefix": stable_prefix,
        "variable_suffix": variable_suffix,
        "workflow": wf,
        "project": project,
        "version": version,
    }


def _workflow_version(brain, spec_rel):
    """Read the '- **Version:** X.Y' line from the workflow spec."""
    for line in _read(brain, spec_rel).splitlines():
        s = line.strip().lstrip("-").strip()
        if s.lower().startswith("**version:**"):
            return s.split("**", 2)[-1].strip()
    return "0"


if __name__ == "__main__":
    a = assemble("net_sec_hardening", "reasoner",
                 goal="Harden a flat home LAN", mode="plan",
                 constraints=["no paid tooling", "single admin"],
                 context="One /24, NAS reachable from all devices.")
    print("cache_key:", a["cache_key"])
    print("stable_prefix bytes:", len(a["stable_prefix"]))
    print("---- variable suffix ----")
    print(a["variable_suffix"])

# workflow_net_sec_hardening.md — Home/Small-Team Network Hardening

- **Workflow id:** `net_sec_hardening`
- **Version:** 1.0
- **Project:** dominion
- **Skeleton:** Security audit
- **Decomposition:** home_network_security_hardening
- **Tradeoff pattern:** security_control_table

## Input schema

```json
{
  "goal": "string — what the user wants secured",
  "mode": "plan | analysis",
  "assets": [{ "name": "string", "type": "router|host|iot|server|service", "exposure": "internal|internet-facing" }],
  "topology": "string — subnets, VLANs, ingress/egress, trust boundaries",
  "constraints": ["string — e.g. no paid tooling, single admin, must stay online"],
  "current_state": "string — existing controls, known gaps"
}
```

## Output schema

```json
{
  "asset_topology_map": "string",
  "threat_model": [{ "asset": "string", "stride": "S|T|R|I|D|E", "threat": "string", "attacker_profile": "string" }],
  "detection": [{ "threat": "string", "signal": "string", "threshold": "string", "action": "string" }],
  "isolation": [{ "measure": "string", "segments": "string", "default_policy": "string" }],
  "remediation_playbooks": [{ "incident_class": "string", "steps": ["string"] }],
  "hardening_baseline": [{ "change": "string", "closes": ["threat"], "phase": "prevent|detect|respond|recover", "home_executable": true }],
  "control_tradeoffs": "security_control_table (filled)",
  "assumptions": ["string"],
  "open_questions": ["string"]
}
```

## Steps

1. **Map assets & topology** (goal: complete inventory; method: walk the
   decomposition tree node 1; verify: every asset in input appears in the map).
2. **Threat model** (goal: STRIDE per boundary; method: realistic home/small-
   team attacker profiles; verify: each internet-facing asset has ≥1 threat).
3. **Design detection** (goal: signal + threshold + action per threat; method:
   only signals available at the user's layers; verify: no "monitor" without
   all three fields — else `monitoring-handwave`).
4. **Isolation strategy** (goal: limit blast radius; method: segmentation +
   default-deny; verify: a compromised device can't reach the trusted segment).
5. **Remediation playbooks** (goal: ordered recovery per incident class;
   method: home-executable steps; verify: each step runnable with owned tools —
   else `non-home-executable`).
6. **Hardening baseline** (goal: preventive changes; method: map each to the
   threat it closes; verify: all four phases prevent/detect/respond/recover are
   represented — else `prevention-only`).

## Error handling

- Missing topology → emit an `open_questions` entry and proceed with a labeled
  assumption; do not invent specifics as fact.
- Constraint conflict (e.g. "no downtime" vs a change that needs a reboot) →
  surface the conflict explicitly; offer both a zero-downtime and a
  maintenance-window option.

## Evidence hooks

Apply `evidence_rules.md` at steps 3, 5, 6. Every hardening change names the
config and the threat it closes; every detection names signal/threshold/action.

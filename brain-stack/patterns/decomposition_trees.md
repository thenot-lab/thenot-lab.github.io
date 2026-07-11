# decomposition_trees.md — Per-Domain Problem Breakdowns

Fixed breakdowns the model walks so nothing structural is skipped. A workflow
names the tree it uses; the model produces analysis at each node.

---

## `home_network_security_hardening`

1. **Asset & topology mapping** — devices, OS/firmware, services, subnets/VLANs,
   ingress/egress, who owns what.
2. **Threat modeling** — per asset and boundary: STRIDE; realistic attacker
   profiles for a home/small-team (not nation-state).
3. **Detection design** — signals available at each layer (router logs, DNS,
   host, IDS); threshold + action per signal.
4. **Isolation strategy** — segmentation (guest/IoT/trusted VLANs), default-deny
   between segments, containment when a device is compromised.
5. **Remediation playbooks** — per incident class: reset, re-image, rotate
   creds, revoke, patch — ordered and home-executable.
6. **Hardening baselines** — router config, firmware policy, unique creds/MFA,
   service minimization, backup + recovery, patch cadence.

---

## `ui_surface`

1. **User + job** — who, what they're trying to accomplish, in what context
   (device, attention, frequency).
2. **State model** — every state: loading, empty, populated, partial, error,
   offline, success. Transitions between them.
3. **Information architecture** — what's shown, hierarchy, what's deferred.
4. **Interaction flow** — primary path, secondary paths, undo/escape hatches.
5. **Edge & failure surfaces** — empty state, error state, latency, permission
   denial, mobile/narrow viewport.
6. **Accessibility & performance** — keyboard, contrast, screen-reader labels,
   payload/render budget.

---

## `agent_bot_capability`

1. **Persona & scope** — identity, allowed topics, refusal boundaries.
2. **Memory model** — what's remembered, scope (per-user/per-thread), TTL,
   storage, privacy.
3. **Model routing** — which model for which request class, and the explicit
   routing rule; fallback on failure.
4. **Tooling / actions** — what the bot can *do*, permissions, irreversible-
   action guards.
5. **Cost & limits** — cost per conversation, caching, batch for bulk jobs,
   rate limits.
6. **Analytics & feedback** — what's measured, how quality is judged, how it
   improves.

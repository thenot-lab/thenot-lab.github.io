#!/usr/bin/env python3
"""
Elli router extension — merges captured device context into the on-device
model's tool surface and chat prompt.

This is the piece that actually *connects* the Eli Companion capture app to
Elli (the on-device SLM served behind tool_router :8081). Without it, Elli
can act on the phone but is blind to everything the companion captured. With
it:

  * Elli gains READ tools (context_digest, recent_notifications,
    usage_summary, recent_messages, search_context, recall) that pull from
    the on-device ContextStore.
  * Every chat turn is grounded: the current device digest is injected into
    the system prompt, so Elli answers "what have I been doing today?"
    without even needing a tool hop.

Dependency-injected on purpose: it takes the router's TOOLS dict and TOOL_SPEC
string as arguments rather than importing tool_router directly, so it can be
(a) unit-tested standalone and (b) wired into the real
`eli/runtime/device_inference/tool_router.py` with three lines (see
`patch_tool_router` docstring). Stdlib only.
"""
from __future__ import annotations

from context_bridge import ContextStore, make_tools, CONTEXT_TOOL_SPEC


def register_context_tools(tools: dict, tool_spec: str, store: ContextStore) -> tuple:
    """Return (merged_tools, merged_spec).

    `tools` / `tool_spec` are the router's existing surface. The returned
    values are new objects — the caller decides whether to rebind the
    router's globals to them (keeps this function pure + testable).
    """
    merged_tools = dict(tools)
    ctx_tools = make_tools(store)
    for name, fn in ctx_tools.items():
        if name in merged_tools:
            raise ValueError(f"context tool name collides with existing router tool: {name}")
        merged_tools[name] = fn
    # Insert the context tools into the spec just before the closing guidance.
    merged_spec = _splice_spec(tool_spec, CONTEXT_TOOL_SPEC)
    return merged_tools, merged_spec


def _splice_spec(base_spec: str, extra: str) -> str:
    """Add the context tools to the router's tool list. If the base spec has
    an 'Available tools:' block we append into it; otherwise we tack it on."""
    marker = "After a tool runs"
    if marker in base_spec:
        head, sep, tail = base_spec.partition(marker)
        return head + extra + sep + tail
    return base_spec + "\n" + extra


def ground_messages(messages: list, store: ContextStore,
                    system_role: str = "system") -> list:
    """Prepend a device-context system message so the model is grounded in the
    phone's current state. Non-destructive: returns a new list.

    The digest is deterministic and derived only from captured rows, so this
    never fabricates context — worst case it says 'No device context yet.'"""
    digest = store.digest()
    grounding = {
        "role": system_role,
        "content": (
            "You are Elli, running on Brayd's own device. The following is "
            "PRIVATE on-device context captured by the Eli Companion app. Use "
            "it to answer grounded questions about the device and Brayd's day. "
            "Never send it anywhere; it stays on this phone.\n\n" + digest
        ),
    }
    return [grounding] + list(messages)


def patch_tool_router(tool_router_module, store: ContextStore | None = None):
    """Wire the context surface into a live tool_router module in place.

    On-device wiring (add to tool_router.main(), or a tiny sitecustomize):

        import elli_router_ext as ext
        ext.patch_tool_router(tool_router)   # after TOOLS/TOOL_SPEC defined

    After this call the router's agent loop can dispatch the context tools and
    (if it uses ground_messages) starts every turn grounded. Returns the
    ContextStore in use so a caller can share it with the ingest endpoint.
    """
    store = store or ContextStore()
    merged_tools, merged_spec = register_context_tools(
        tool_router_module.TOOLS, tool_router_module.TOOL_SPEC, store,
    )
    tool_router_module.TOOLS = merged_tools
    tool_router_module.TOOL_SPEC = merged_spec
    return store

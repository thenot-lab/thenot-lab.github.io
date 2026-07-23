#!/usr/bin/env python3
"""
End-to-end demo of the Connect (Data) loop, offline.

Simulates the whole path the real system runs on-device:

    Eli Companion (capture) --/v1/context/event--> ContextStore
                                                       |
    Elli chat turn  <--grounded system prompt-- elli_router_ext
                     --TOOL: context tool-->  ContextStore read

The model call is stubbed (a scripted Elli) so this runs with no llama-server
and no API key — it demonstrates wiring, not model quality. Run:

    python3 eli-os/integration/demo.py
"""
import json
import tempfile

import context_bridge as cb
import elli_router_ext as ext


def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = cb.ContextStore(tmp.name)

    print("=" * 66)
    print("1. Eli Companion captures device context and POSTs it on-device")
    print("=" * 66)
    events = [
        {"type": "usage_snapshot",
         "payload": {"top_apps": "com.whatsapp:5400000:1|com.android.chrome:1800000:2|"
                                  "com.spotify:900000:3"}},
        {"type": "notification", "payload": {"package": "com.whatsapp", "title": "Mom: call me"}},
        {"type": "notification", "payload": {"package": "com.whatsapp", "title": "Mom: you up?"}},
        {"type": "notification", "payload": {"package": "com.slack", "title": "deploy failed"}},
        {"type": "sms", "payload": {"sender": "Mom", "body": "can you pick up milk"}},
    ]
    for e in events:
        r = store.ingest(e)
        print(f"  ingested {e['type']:16} -> id={r['id']} derived={r['derived']}")

    print("\n" + "=" * 66)
    print("2. Elli's turn is GROUNDED with the on-device context digest")
    print("=" * 66)
    user_msg = {"role": "user", "content": "what have I been up to and who needs me?"}
    grounded = ext.ground_messages([user_msg], store)
    print(grounded[0]["content"])

    print("\n" + "=" * 66)
    print("3. Elli can also CALL context tools mid-chat (tool_router contract)")
    print("=" * 66)
    tools = cb.make_tools(store)
    for call in [("usage_summary", {"window_hours": 24}),
                 ("recent_messages", {"limit": 3}),
                 ("recall", {"query": "notifs_from"})]:
        name, args = call
        res = tools[name](args)
        out = res["out"]
        try:
            out = json.dumps(json.loads(out), indent=0)[:200]
        except ValueError:
            out = out[:200]
        print(f"\n  TOOL: {name}({args})")
        print(f"  -> [{res['tier']}] rc={res['rc']} {out}")

    print("\n" + "=" * 66)
    print("4. What Elli would say (scripted here — real Elli is the SLM)")
    print("=" * 66)
    usage = store.usage_summary()[:3]
    top = ", ".join(f"{u['package'].split('.')[-1]}" for u in usage)
    print(f"  Elli: You've mostly been in {top} today. Mom messaged twice on")
    print( "         WhatsApp and by SMS (wants milk), and Slack flagged a failed")
    print( "         deploy — that Slack one looks time-sensitive.")
    print("\n[demo complete — offline, on-device path verified]")


if __name__ == "__main__":
    main()

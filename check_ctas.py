#!/usr/bin/env python3
"""Is every way to give us money actually reachable?

WHY THIS EXISTS. On 2026-09-01 `curl` reported eight Stripe payment links live; seven
were dead. A DEACTIVATED Stripe link returns HTTP 200 and a byte-identical ~560 KB JS
shell -- the words "inactive", "deactivated" and "expired" all appear in that shell
because they are strings in the bundle, not a status. So an HTTP check on a payment
link is not a weak signal, it is NO signal, and it renders green.

The fix is not a better HTTP check. It is refusing to report green for something that
was never measured. Payment links come back UNVERIFIABLE, loudly, with the reason and
the one instrument that can settle it. Everything genuinely checkable IS checked.

Exit 1 on any DEAD link. Exit 2 when the only revenue path is UNVERIFIABLE -- because
"we cannot tell whether anyone can pay us" is a finding, not a pass.
"""
from __future__ import annotations
import datetime as _dt
import json, re, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NLI = chr(10)


# HUMAN VERIFICATION, CARRIED FORWARD AND AGED.
# HTTP cannot separate a live payment link from a dead one -- both return 200 and a
# byte-identical shell. A person in a browser can: a live link renders a Pay button,
# a dead one renders "no longer active" and offers nothing to click.
#
# Throwing that answer away on every run would be as dishonest as inventing one. So it
# is recorded in cta_verified.json -- and it EXPIRES. A confirmation from six months ago
# is not a confirmation, and stale must read as unverified rather than quietly as green.
def _load_verified():
    f = ROOT / "cta_verified.json"
    if not f.exists():
        return {}, 30
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: cta_verified.json is unreadable ({e}); treating all links as unverified")
        return {}, 30
    return d.get("verified", {}), int(d.get("stale_after_days", 30))


VERIFIED, STALE_DAYS = _load_verified()


def _verdict(url):
    """Return (state, note) where state is 'fresh', 'stale' or 'none'."""
    rec = VERIFIED.get(url)
    if not rec:
        return "none", ""
    try:
        age = (_dt.date.today() - _dt.date.fromisoformat(rec["date"])).days
    except Exception:
        return "none", ""
    who = rec.get("by", "unknown")
    if age > STALE_DAYS:
        return "stale", f'last confirmed {rec["date"]} by {who} -- {age}d old, past the {STALE_DAYS}d window'
    return "fresh", f'confirmed LIVE {rec["date"]} by {who} ({age}d ago) -- {rec.get("evidence", "")}'

UA = {"User-Agent": "Mozilla/5.0 (compatible; DominionCTACheck/1.0)"}
HREF = re.compile(r'href="([^"]+)"')
DLMAIL = re.compile(r'class="[^"]*dl-mail')
HYDRATE = re.compile(r"querySelectorAll\('a\.dl-mail'\)")

def head(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, len(r.read(2048))
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:
        return None, str(e)[:60]

dead, unverifiable, ok, notes = [], [], [], []
pages = sorted(ROOT.glob("*.html"))
if not pages:
    print("no pages found"); sys.exit(1)

for p in pages:
    html = p.read_text(encoding="utf-8", errors="replace")
    hrefs = HREF.findall(html)

    # 1. obfuscated email CTAs are only real if the page also ships the hydrator
    anchors = len(DLMAIL.findall(html))
    if anchors and not HYDRATE.search(html):
        dead.append(f"{p.name}: {anchors} dl-mail CTA(s) but NO hydration script -> href stays '#'")
    elif anchors:
        ok.append(f"{p.name}: {anchors} email CTA(s) hydrated")

    for h in hrefs:
        if h.startswith("#") or h.startswith("mailto:"):
            continue
        if "fonts.googleapis" in h or "fonts.gstatic" in h:
            continue

        if "buy.stripe.com" in h or "checkout.stripe.com" in h:
            st, _ = head(h)
            # 200 here means the SHELL loaded. It does not mean the link is active.
            state, note = _verdict(h)
            if st is None or st >= 400:
                dead.append(f"{p.name}: {h} -> HTTP {st} -- the shell itself did not load")
            elif state == "fresh":
                ok.append(f"{p.name}: {h}" + NLI + f"      HTTP {st}, and {note}")
            elif state == "stale":
                unverifiable.append(
                    f"{p.name}: {h}" + NLI
                    + f"      HTTP {st} proves nothing here, and the human check EXPIRED." + NLI
                    + f"      {note}" + NLI
                    + "      Re-open it in a browser and update cta_verified.json."
                )
            else:
                unverifiable.append(
                    f"{p.name}: {h}" + NLI
                    + f"      HTTP {st} -- but a deactivated link returns 200 and an identical shell." + NLI
                    + "      Settle it in a real browser, then record it in cta_verified.json."
                )
            continue

        if h.startswith("http"):
            st, extra = head(h)
            (ok if st and st < 400 else dead).append(f"{p.name}: {h} -> {st or extra}")
        else:
            target = ROOT / h.split("#")[0].split("?")[0].lstrip("/")
            (ok if target.exists() else dead).append(
                f"{p.name}: {h} -> {'ok' if target.exists() else 'MISSING FILE'}")

print("=" * 72)
print(f"CTA CHECK -- {len(pages)} page(s)")
print("=" * 72)
print(f"\nOK ({len(ok)}):")
for x in ok: print(f"  + {x}")
if unverifiable:
    print(f"\nUNVERIFIABLE ({len(unverifiable)}) -- NOT a pass:")
    for x in unverifiable: print(f"  ? {x}")
if dead:
    print(f"\nDEAD ({len(dead)}):")
    for x in dead: print(f"  X {x}")

if dead:
    print("\nVERDICT: DEAD LINKS PRESENT"); sys.exit(1)
if unverifiable:
    print("\nVERDICT: no dead links, but the revenue path is UNVERIFIABLE by HTTP.")
    print("A payment link cannot be proven live from here. That is the finding.")
    sys.exit(2)
print("\nVERDICT: all CTAs verified"); sys.exit(0)

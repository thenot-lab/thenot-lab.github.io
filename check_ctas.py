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
import re, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
            unverifiable.append(
                f"{p.name}: {h}\n"
                f"      HTTP {st} -- but a deactivated link returns 200 and an identical shell.\n"
                f"      Settle it with: a real browser, or the Stripe dashboard/API."
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

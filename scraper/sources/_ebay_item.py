"""Fetch seller-trust info from an individual eBay item page.

eBay's search-results page (SRP) for active listings does NOT include
seller info on the listing cards — that info is only on the per-item
view. This module is the cheapest possible follow-up: hit the item URL,
regex out the embedded JSON's seller fields, return them.

We extract three signals:
- seller_name        (e.g. "Arcturus TCG")
- seller_items_sold  (lifetime sold count for the seller, e.g. 385)
- seller_positive_pct (e.g. 100.0)

Modern eBay item pages no longer expose the legacy "feedback score"
prominently — "items sold" + "% positive" is the current trust UI eBay
itself shows the buyer, and is what we surface to the user.

Failure mode: any field that can't be extracted is None. Caller renders
an UNKNOWN pill; the listing is never dropped.
"""
from __future__ import annotations

import re
import requests

from ._browser import USER_AGENT


# The seller block on a modern eBay item page is rendered from JSON
# embedded in the HTML. The JSON path is structured roughly:
#   ...sellerCard...headline.text=="<seller name>"
#   ...trustSignals[..text=="100% positive"]
#   ...trustSignals[..text=="385 items sold"]
#
# We extract by regex over the source text rather than parsing the JSON
# (the surrounding wrapper is a 700KB React-hydration blob with no
# stable JSON-pointer API). Patterns are anchored to the seller card so
# they don't match other "items sold" text elsewhere on the page.

_SELLER_NAME_RE = re.compile(
    # The seller card's headline holds the seller name. Match either the
    # textSpans path (most common) or the bare "text":"..." pair near a
    # nearby "items sold" marker. We use a permissive .{0,400} to tolerate
    # nested JSON between the "headline" key and the actual text.
    r'"headline"\s*:\s*\{.{0,400}?"text"\s*:\s*"([^"]+)"',
    re.S,
)
# Captures plain ints, commas (385, 1,234), and K/M shorthand (89K, 1.5M).
_ITEMS_SOLD_RE = re.compile(r'(\d+(?:[,.]\d+)?[KkMm]?)\s+items?\s+sold', re.I)
_POSITIVE_PCT_RE = re.compile(r'(\d+(?:\.\d+)?)%\s*positive', re.I)


def _parse_items_sold(raw: str) -> int | None:
    """'385' -> 385, '1,234' -> 1234, '89K' -> 89000, '1.5M' -> 1500000."""
    if not raw:
        return None
    s = raw.strip().replace(",", "")
    mult = 1
    if s.endswith(("K", "k")):
        mult = 1_000
        s = s[:-1]
    elif s.endswith(("M", "m")):
        mult = 1_000_000
        s = s[:-1]
    try:
        return int(round(float(s) * mult))
    except ValueError:
        return None


def parse(html: str) -> dict:
    """Extract seller-trust signals from an eBay item-page HTML string."""
    name = None
    m = _SELLER_NAME_RE.search(html)
    if m:
        name = m.group(1).strip() or None

    items_sold = None
    m = _ITEMS_SOLD_RE.search(html)
    if m:
        items_sold = _parse_items_sold(m.group(1))

    positive_pct = None
    m = _POSITIVE_PCT_RE.search(html)
    if m:
        try:
            positive_pct = float(m.group(1))
        except ValueError:
            positive_pct = None

    return {
        "seller_name": name,
        "seller_items_sold": items_sold,
        "seller_positive_pct": positive_pct,
    }


def fetch_seller(item_url: str, locale: str = "en-GB", timeout: int = 15) -> dict:
    """Fetch an eBay item URL via plain HTTP and return seller-trust signals.

    Works for eBay UK item pages. eBay US item pages return a 13KB JS
    shell to vanilla requests from datacenter IPs — for those, prefer
    ``fetch_sellers_rendered`` which routes through patchright.

    Returns a dict with three keys (any may be None on parse miss).
    Returns all-None on network failure — never raises into the caller.
    """
    try:
        r = requests.get(
            item_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": f"{locale},en;q=0.9",
            },
            timeout=timeout,
        )
        r.raise_for_status()
    except Exception:
        return {"seller_name": None, "seller_items_sold": None, "seller_positive_pct": None}
    return parse(r.text)


def fetch_sellers_rendered(item_urls: list[str], locale: str = "en-US") -> dict[str, dict]:
    """Fetch multiple eBay item URLs through ONE patchright browser.

    For eBay US, where plain HTTP returns a JS shell. Reuses one browser
    session for all URLs — pays the ~5-15s Chromium spin-up once, not
    per-URL. Returns ``{url: {seller_name, seller_items_sold,
    seller_positive_pct}}``. Empty/failed URLs get all-None values.
    """
    if not item_urls:
        return {}
    # Lazy import: keep _ebay_item importable in environments without
    # patchright (e.g. lint runs over the parser tests).
    from ._browser import render_many

    htmls = render_many(item_urls, locale=locale, selector_timeout_ms=5000)
    return {url: parse(html) if html else
            {"seller_name": None, "seller_items_sold": None, "seller_positive_pct": None}
            for url, html in htmls.items()}

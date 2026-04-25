"""User-pinned eBay item-page source.

eBay UK refuses to serve active-listing SRP results to GitHub Actions
IPs (every URL variant + filter combination hangs patchright). This
source side-steps the SRP entirely: the user can paste an eBay URL
they spotted and it gets fetched directly as an item page (which
patchright DOES handle reliably for both .co.uk and .com).

To add a listing, append a tuple to ``PINNED_ITEMS``. The orchestrator
filters and dedupes the results against the live eBay-active rows so
removing a listing is also safe — when the seller delists, the item
page returns a "no longer available" page and our parser drops it.

Each pinned entry is ``("ebay_uk" | "ebay_us", "<item_id>")``. The
item id is the digits in the eBay URL between ``/itm/`` and the ``?``.
"""
from __future__ import annotations

import re

from ._browser import render_many
from ._ebay_item import parse as parse_seller
from ._filter import is_acceptable


# Add tuples below to track specific eBay listings. Format:
#   ("ebay_uk", "198215232725")  — for https://www.ebay.co.uk/itm/198215232725
#   ("ebay_us", "285176228006")  — for https://www.ebay.com/itm/285176228006
PINNED_ITEMS: list[tuple[str, str]] = [
    ("ebay_uk", "198215232725"),  # Sealed 1999 Pokemon Base Set Booster Box, £35k
]


_TITLE_RE = re.compile(
    # eBay's modern item page embeds the listing title in a JSON blob:
    # "title":"<the actual title>"  near the start of the page.
    r'"title"\s*:\s*"((?:[^"\\]|\\.){10,200})"',
)
_GBP_RE = re.compile(r'(?:£|GBP\s*)\s*([\d,]+(?:\.\d{2})?)')
_USD_RE = re.compile(r'\$\s*([\d,]+(?:\.\d{2})?)')


def _unescape_json(s: str) -> str:
    """Decode JSON-escaped chars (\\u00e9, \\", \\n) without parsing JSON."""
    try:
        return s.encode("utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return s


def _parse_title(html: str) -> str | None:
    m = _TITLE_RE.search(html)
    if not m:
        # Fallback: <title> tag (eBay format: "<listing> | eBay")
        m2 = re.search(r"<title>(.+?)\s*\|\s*eBay</title>", html)
        return m2.group(1).strip() if m2 else None
    return _unescape_json(m.group(1)).strip()


def _parse_price_cents(html: str, currency: str) -> int | None:
    """Extract price in cents/pence. Currency = '£' or '$'."""
    rx = _GBP_RE if currency == "£" else _USD_RE
    matches = rx.findall(html)
    if not matches:
        return None
    # Item pages can list multiple prices (current, original, shipping).
    # The current price is usually the first or smallest plausible value.
    # Take the largest match in the price band — current price for an
    # Unlimited box is always five figures, so $ shipping fees etc. drop
    # out naturally.
    plausible = []
    for m in matches:
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        if 5_000 <= v <= 200_000:  # in dollars or pounds, both work
            plausible.append(v)
    if not plausible:
        return None
    return int(round(max(plausible) * 100))


def parse_item(html: str, locale: str) -> dict | None:
    """Parse one eBay item-page HTML into an active-listing row."""
    title = _parse_title(html)
    if not title:
        return None
    if locale == "ebay_uk":
        gbp_cents = _parse_price_cents(html, "£")
        if gbp_cents is None:
            return None
        # Convert to USD so the filter can compare against its band.
        # We don't have FX here — the orchestrator will fix gbp/usd
        # values into the snapshot. For filter purposes use a rough
        # 0.78 conversion (close enough for in-band check).
        approx_usd = (gbp_cents / 100.0) / 0.78
        if not is_acceptable(title, approx_usd):
            return None
        return {
            "source": "ebay_uk",
            "title": title,
            "gbp_cents": gbp_cents,
            "usd_cents": int(round(approx_usd * 100)),  # orchestrator may overwrite via FX
            "date": None,
        }
    else:  # ebay_us
        usd_cents = _parse_price_cents(html, "$")
        if usd_cents is None:
            return None
        usd = usd_cents / 100.0
        if not is_acceptable(title, usd):
            return None
        return {
            "source": "ebay_us",
            "title": title,
            "usd_cents": usd_cents,
            "date": None,
        }


def fetch(gbp_per_usd: float = 0.78) -> list[dict]:
    """Fetch every pinned item page and return acceptable rows.

    Uses one patchright session for all URLs (cookie/fingerprint
    reuse). Each row also gets seller name + items-sold + positive %
    pulled from the same page.
    """
    if not PINNED_ITEMS:
        return []

    # Group pinned items by locale so we issue one batched render per
    # eBay TLD (en-GB vs en-US) — matters because patchright sets the
    # browser locale per session and price formatting differs.
    by_locale: dict[str, list[str]] = {"ebay_uk": [], "ebay_us": []}
    for src, item_id in PINNED_ITEMS:
        if src == "ebay_uk":
            by_locale["ebay_uk"].append(f"https://www.ebay.co.uk/itm/{item_id}")
        else:
            by_locale["ebay_us"].append(f"https://www.ebay.com/itm/{item_id}")

    import sys
    out: list[dict] = []
    for src, urls in by_locale.items():
        if not urls:
            continue
        locale = "en-GB" if src == "ebay_uk" else "en-US"
        print(f"DEBUG: ebay_pinned: rendering {len(urls)} {src} urls", file=sys.stderr, flush=True)
        try:
            htmls = render_many(urls, locale=locale, selector_timeout_ms=8000)
        except Exception as e:
            print(f"DEBUG: ebay_pinned: render_many raised: {e!r}", file=sys.stderr, flush=True)
            continue
        for url, html in htmls.items():
            if not html:
                print(f"DEBUG: ebay_pinned: empty html for {url}", file=sys.stderr, flush=True)
                continue
            row = parse_item(html, src)
            if not row:
                print(f"DEBUG: ebay_pinned: parse_item returned None for {url} (html={len(html)}b)",
                      file=sys.stderr, flush=True)
                continue
            row["url"] = url
            # Pull seller-trust signals from the same HTML.
            seller = parse_seller(html)
            row["seller_name"] = seller.get("seller_name")
            row["seller_feedback"] = seller.get("seller_items_sold")
            row["seller_positive_pct"] = seller.get("seller_positive_pct")
            # If we couldn't read seller info the row would render as a
            # grey "?" pill; prefer to drop pinned items with no seller
            # info rather than show a useless row.
            if row["seller_positive_pct"] is None and not row["seller_name"]:
                print(f"DEBUG: ebay_pinned: no seller signals for {url} (title={row['title'][:40]!r})",
                      file=sys.stderr, flush=True)
                continue
            # Convert GBP rows to USD using the live FX (filter used a
            # rough 0.78 estimate; this is the precise number).
            if src == "ebay_uk":
                gbp = row["gbp_cents"] / 100.0
                row["usd_cents"] = int(round(gbp / gbp_per_usd * 100))
            out.append(row)
    return out

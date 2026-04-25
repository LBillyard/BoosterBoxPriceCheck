"""eBay UK *active* (Buy It Now) listings source.

Mirrors :mod:`scraper.sources.ebay_uk` but targets the live SRP — items
currently for sale, not sold completes. The URL drops ``LH_Sold=1`` and
``LH_Complete=1`` and adds ``LH_BIN=1`` (Buy It Now only) so we don't
mix in active auctions whose price moves over time.

Output uses the same dict shape as the sold parser, except ``date`` is
always ``None`` (an active listing has no sale date). The orchestrator
projects these into ``snapshot.active_listings``.

The DOM is the same React-rendered SRP eBay ships everywhere — we reuse
the sold parser's helpers (``_parse_gbp``, ``_clean_title``) and the
shared filter to reject 1st Edition / reprint / out-of-band noise.
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from ._browser import fetch_html, render
from ._filter import is_acceptable
from ._ebay_item import fetch_sellers_rendered
from .ebay_uk import _parse_gbp, _clean_title, _PLACEHOLDER_TITLE
from .ebay_us import _seller_from_card

# URL fallback chain. The original (LH_BIN=1 + _sop=15 + _udlo) was
# observed to hang patchright 100% of the time — eBay UK appears to
# treat the BIN-only / lowest-price-first SRP as bot-sensitive and
# never finishes serving the hydrated page. The other variants drop
# either LH_BIN, the price floor, or the sort to find an SRP that
# patchright can render. We try in order; first one that produces any
# accepted listing wins.
URL_VARIANTS = (
    # Default sort (best match), no BIN/sort/floor — most permissive.
    "https://www.ebay.co.uk/sch/i.html?_nkw=pokemon+base+set+booster+box+wotc",
    # Vintage-targeted query.
    "https://www.ebay.co.uk/sch/i.html?_nkw=pokemon+1999+base+set+booster+box+sealed",
    # All listings (auction + BIN), price ascending, no floor.
    "https://www.ebay.co.uk/sch/i.html?_nkw=pokemon+base+set+booster+box+wotc&_sop=15",
)
# Kept for backwards compatibility with imports / scripts that
# reference the original constant.
URL = URL_VARIANTS[0]


def parse(html: str, gbp_per_usd: float) -> list[dict]:
    """Parse eBay UK active-listings HTML into normalised dicts.

    Returns items shaped::

        {"source": "ebay_uk", "title": str, "usd_cents": int,
         "gbp_cents": int, "date": None, "url": str | None}
    """
    if gbp_per_usd <= 0:
        raise ValueError("gbp_per_usd must be > 0")

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []

    for card in soup.find_all(class_="s-card"):
        title_el = card.find(class_="s-card__title")
        if not title_el:
            continue
        title = _clean_title(title_el.get_text(" ", strip=True))
        if not title or _PLACEHOLDER_TITLE.match(title):
            continue

        price_el = card.find(class_="s-card__price")
        if not price_el:
            continue
        gbp_cents = _parse_gbp(price_el.get_text(" ", strip=True))
        if gbp_cents is None:
            continue

        usd = (gbp_cents / 100.0) / gbp_per_usd
        usd_cents = int(round(usd * 100))

        if not is_acceptable(title, usd):
            continue

        url = None
        link = card.find("a", class_="s-card__link", href=True)
        if link:
            url = link["href"]

        seller_name, seller_feedback, seller_positive_pct = _seller_from_card(card)

        out.append(
            {
                "source": "ebay_uk",
                "title": title,
                "usd_cents": usd_cents,
                "gbp_cents": gbp_cents,
                "date": None,
                "url": url,
                "seller_name": seller_name,
                "seller_feedback": seller_feedback,
                "seller_positive_pct": seller_positive_pct,
            }
        )

    return out


def fetch(gbp_per_usd: float) -> list[dict]:
    """Hit eBay UK active-listings SRP via patchright-driven Chromium.

    Plain HTTP returns a 13KB JS shell from datacenter IPs. The SRP
    also doesn't include seller info on the listing cards, so we
    follow up on each accepted listing with a per-item-page fetch
    (plain HTTP works for UK item pages) to extract seller name +
    items-sold + positive %. Drops listings whose item page didn't
    render — without seller trust signals the user can't judge
    legitimacy.

    Uses a URL fallback chain — the original BIN+sort+floor combo
    hangs patchright. Tries each URL in order; first one that yields
    parsed listings (before the seller-info filter) wins. Per-URL
    timeout is short (30s) so the whole chain fits inside the
    orchestrator's per-source budget.
    """
    listings: list[dict] = []
    for url in URL_VARIANTS:
        try:
            html = render(
                url,
                wait_selector="div.s-card",
                timeout_ms=30000,
                selector_timeout_ms=12000,
                locale="en-GB",
            )
        except Exception:
            continue
        listings = parse(html, gbp_per_usd)
        if listings:
            break
    # Batch item-page renders through patchright — eBay UK item pages
    # now return a JS shell to plain HTTP from datacenter IPs, same as
    # the SRP, so we use the rendered path for both.
    item_urls = [it["url"] for it in listings if it.get("url") and not it.get("seller_name")]
    if item_urls:
        try:
            sellers = fetch_sellers_rendered(item_urls, locale="en-GB")
        except Exception:
            sellers = {}
        for item in listings:
            url = item.get("url")
            if url and url in sellers:
                s = sellers[url]
                item["seller_name"] = s.get("seller_name")
                item["seller_feedback"] = s.get("seller_items_sold")
                item["seller_positive_pct"] = s.get("seller_positive_pct")
    # Same drop-on-no-trust-signals rule as ebay_us_active so the UI
    # never shows a row whose seller we couldn't read.
    return [
        it for it in listings
        if it.get("seller_name") or it.get("seller_positive_pct") is not None
    ]


def parse_fixture(path: str | Path, gbp_per_usd: float) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"), gbp_per_usd)

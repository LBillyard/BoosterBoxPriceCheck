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

from ._browser import fetch_html
from ._filter import is_acceptable
from ._ebay_item import fetch_seller
from .ebay_uk import _parse_gbp, _clean_title, _PLACEHOLDER_TITLE
from .ebay_us import _seller_from_card

URL = (
    "https://www.ebay.co.uk/sch/i.html"
    "?_nkw=pokemon+base+set+booster+box+wotc"
    "&LH_BIN=1&_sop=15&_udlo=10000"
)


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
    """Hit eBay UK active-listings SRP via plain HTTP (no JS needed).

    The SRP doesn't include seller info on the listing cards, so we
    follow up on each accepted listing with a per-item-page fetch to
    extract seller name + items-sold + positive %.
    """
    try:
        html = fetch_html(URL, locale="en-GB")
    except Exception:
        return []
    listings = parse(html, gbp_per_usd)
    for item in listings:
        if not item.get("seller_name") and item.get("url"):
            seller = fetch_seller(item["url"], locale="en-GB")
            item["seller_name"] = seller.get("seller_name")
            item["seller_feedback"] = seller.get("seller_items_sold")
            item["seller_positive_pct"] = seller.get("seller_positive_pct")
    return listings


def parse_fixture(path: str | Path, gbp_per_usd: float) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"), gbp_per_usd)

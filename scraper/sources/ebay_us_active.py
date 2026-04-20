"""eBay US *active* (Buy It Now) listings source.

Mirrors :mod:`scraper.sources.ebay_us` but targets the live SRP.
``LH_BIN=1`` (Buy It Now only) without ``LH_Sold=1&LH_Complete=1``
returns items currently for sale.

Output shape matches the sold parser, except ``date`` is ``None``.

Transport: same as the sold variant — patchright-driven Chromium via
:func:`scraper.sources._browser.render`, because eBay US's bot detector
serves a JS-shell to vanilla HTTP from datacenter IPs.
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from ._browser import render
from ._filter import is_acceptable
from ._ebay_item import fetch_sellers_rendered
from .ebay_us import _parse_usd, _clean_title, _PLACEHOLDER_TITLE, _seller_from_card

URL = (
    "https://www.ebay.com/sch/i.html"
    "?_nkw=pokemon+base+set+booster+box+wotc"
    "&LH_BIN=1&_sop=15"
)


def parse(html: str) -> list[dict]:
    """Parse eBay US active-listings HTML into normalised dicts.

    Returns items shaped::

        {"source": "ebay_us", "title": str, "usd_cents": int,
         "date": None, "url": str | None}
    """
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
        usd_cents = _parse_usd(price_el.get_text(" ", strip=True))
        if usd_cents is None:
            continue

        usd = usd_cents / 100.0
        if not is_acceptable(title, usd):
            continue

        url = None
        link = card.find("a", class_="s-card__link", href=True)
        if link:
            url = link["href"]

        seller_name, seller_feedback, seller_positive_pct = _seller_from_card(card)

        out.append(
            {
                "source": "ebay_us",
                "title": title,
                "usd_cents": usd_cents,
                "date": None,
                "url": url,
                "seller_name": seller_name,
                "seller_feedback": seller_feedback,
                "seller_positive_pct": seller_positive_pct,
            }
        )

    return out


def fetch(timeout_ms: int = 45000) -> list[dict]:
    """Hit eBay US active-listings SRP via patchright-driven Chromium.

    See :func:`scraper.sources.ebay_us.fetch` for why we render rather
    than plain-HTTP this source. The SRP doesn't include seller info
    on the cards, so we follow up with a single patchright session that
    visits every accepted item URL in one browser context to extract
    seller trust signals (plain HTTP returns a JS shell from datacenter
    IPs for the US item view).
    """
    try:
        html = render(
            URL,
            wait_selector="div.s-card",
            timeout_ms=timeout_ms,
            selector_timeout_ms=20000,
            locale="en-US",
        )
    except Exception:
        return []
    listings = parse(html)

    # Batch-render every item page in a single browser session to get
    # seller name + items-sold + positive %. One Chromium spin-up,
    # multiple navigations, shared cookies/fingerprint.
    item_urls = [it["url"] for it in listings if it.get("url") and not it.get("seller_name")]
    if item_urls:
        try:
            sellers = fetch_sellers_rendered(item_urls, locale="en-US")
        except Exception:
            sellers = {}
        for item in listings:
            url = item.get("url")
            if url and url in sellers:
                s = sellers[url]
                item["seller_name"] = s.get("seller_name")
                item["seller_feedback"] = s.get("seller_items_sold")
                item["seller_positive_pct"] = s.get("seller_positive_pct")
    return listings


def parse_fixture(path: str | Path) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"))

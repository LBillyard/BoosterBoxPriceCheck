"""eBay US sold-listings source.

A near-mirror of :mod:`scraper.sources.ebay_uk`, but pointed at ``ebay.com``
and parsing USD prices directly (no FX conversion). Added because the UK
SRP for "pokemon base set booster box" rarely surfaces vintage Unlimited
sales — the US market has far higher liquidity for sealed WOTC product, so
``ebay_us`` is the source most likely to actually return rows on any given
day.

The DOM and class names are identical to eBay UK (eBay ships the same
React-rendered SRP component to both sites). Only the price regex and the
date format differ:

* Prices: ``$36,600.00`` / occasionally ``$30,000.00 to $35,000.00``
* Dates: ``Sold  Mar 10, 2026`` (US format, no leading day)

We split the implementation into its own file rather than parameterising
``ebay_uk`` because (a) the snapshot uses ``source`` field to badge each
row in the web UI ("ebay.co.uk" vs "ebay.com") and (b) the orchestrator
gets to isolate the two fetches — if eBay UK rate-limits us today, the US
result still lands.
"""
from __future__ import annotations

import re
import datetime as dt
from pathlib import Path

from bs4 import BeautifulSoup

from ._browser import render
from ._filter import is_acceptable

# Search query notes: see ``ebay_uk.py``. ``_udlo=15000`` (min $15k) keeps
# modern reprints out of the SRP entirely.
URL = (
    "https://www.ebay.com/sch/i.html"
    "?_nkw=pokemon+base+set+booster+box+wotc"
    "&LH_Sold=1&LH_Complete=1&_sop=13&_udlo=15000"
)

_USD_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
# eBay US sold caption: "Sold  Mar 10, 2026"  (sometimes "Sold Mar 10, 2026")
_DATE_RE = re.compile(
    r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b"
)
_PLACEHOLDER_TITLE = re.compile(r"^shop on ebay$", re.I)
_TRAILING_NOISE = re.compile(r"\s*opens in a new window or tab\s*$", re.I)
_LEADING_NOISE = re.compile(r"^\s*new\s+listing\s+", re.I)


def _parse_usd(text: str) -> int | None:
    """Parse '$36,600.00' or '$30,000.00 to $35,000.00' into integer cents.

    For ranges we take the lower bound (conservative).
    """
    if not text:
        return None
    matches = _USD_RE.findall(text)
    if not matches:
        return None
    try:
        values = [float(m.replace(",", "")) for m in matches]
    except ValueError:
        return None
    return int(round(min(values) * 100))


def _parse_date(text: str) -> str | None:
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _clean_title(text: str) -> str:
    text = _LEADING_NOISE.sub("", text)
    text = _TRAILING_NOISE.sub("", text)
    return text.strip()


def parse(html: str) -> list[dict]:
    """Parse eBay US sold-listings HTML into normalised sale dicts.

    Returns items shaped::

        {"source": "ebay_us", "title": str, "usd_cents": int,
         "date": "YYYY-MM-DD" | None, "url": str | None}
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

        cap_el = card.find(class_="s-card__caption")
        date_iso = _parse_date(cap_el.get_text(" ", strip=True)) if cap_el else None

        url = None
        link = card.find("a", class_="s-card__link", href=True)
        if link:
            url = link["href"]

        out.append(
            {
                "source": "ebay_us",
                "title": title,
                "usd_cents": usd_cents,
                "date": date_iso,
                "url": url,
            }
        )

    return out


def fetch(timeout_ms: int = 45000) -> list[dict]:
    """Hit eBay US's sold-listings page via headless Chromium.

    Returns an empty list on Playwright failure; orchestrator isolates.
    """
    try:
        html = render(
            URL,
            wait_selector=".srp-results, .s-item, .s-card",
            timeout_ms=timeout_ms,
        )
    except Exception:
        return []
    return parse(html)


def parse_fixture(path: str | Path) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"))

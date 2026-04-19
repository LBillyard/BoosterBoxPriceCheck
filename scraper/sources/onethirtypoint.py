"""130point.com sold-sales source.

130point.com is a sales aggregator that surfaces eBay/PWCC sold rows. The
public ``/sales/`` page renders results in a table; each row has a title
cell, a USD price cell, a sold-date cell, and (usually) an outbound link
back to the original listing.

NOTE on Cloudflare: 130point.com sits behind a Cloudflare managed challenge
that returns HTTP 403 + a "Just a moment..." interstitial to plain HTTP
clients (curl, requests). A live scrape from CI will currently yield zero
sales. The orchestrator wraps ``fetch()`` in try/except so this is a soft
failure — the snapshot still ships with eBay/PriceCharting data. The follow
up to fully unlock 130point is to drive it through Playwright with a real
browser fingerprint; the parser below is structured to keep working once
real HTML reaches it.

The parser is deliberately permissive about row markup — it scans every
``<tr>`` looking for a price-shaped cell, a date-shaped cell, and a link or
title text. That makes it robust to small variations in 130point's layout
(they have shipped at least two table redesigns in the last year).
"""
from __future__ import annotations

import re
import datetime as dt
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ._filter import is_acceptable

URL = "https://130point.com/sales/?search=base+set+booster+box&sort=date"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%b %d %Y",
    "%B %d, %Y",
    "%d %b %Y",
)
_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATE_LOOSE_RE = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)


def _parse_price(text: str) -> int | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "")) * 100))
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    if not text:
        return None
    iso = _ISO_RE.search(text)
    if iso:
        return iso.group(1)
    m = _DATE_LOOSE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse(html: str) -> list[dict]:
    """Parse a 130point sales-page HTML blob into normalised sale dicts.

    Returns items shaped::

        {"source": "130point", "title": str, "usd_cents": int,
         "date": "YYYY-MM-DD", "url": str | None}

    Only items passing :func:`is_acceptable` (sealed Unlimited Base Set
    Booster Box, in plausible price band) are returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []

    for row in soup.find_all("tr"):
        text = row.get_text(" ", strip=True)
        if "$" not in text:
            continue
        cents = _parse_price(text)
        if cents is None:
            continue

        # Title: prefer an explicit title cell; fall back to the row's first
        # anchor text or the longest <td> text.
        title = None
        for sel in ("td.title", "td.item-title", "td.name", "td.item"):
            cell = row.select_one(sel)
            if cell:
                title = cell.get_text(" ", strip=True)
                break
        if not title:
            anchor = row.find("a")
            if anchor:
                title = anchor.get_text(" ", strip=True)
        if not title:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            cells = [c for c in cells if c]
            if cells:
                title = max(cells, key=len)
        if not title:
            continue

        # Date: scan dedicated cells first, then row text.
        date_iso = None
        for sel in ("td.date", "td.sold-date", "td.sale-date"):
            cell = row.select_one(sel)
            if cell:
                date_iso = _parse_date(cell.get_text(" ", strip=True))
                if date_iso:
                    break
        if not date_iso:
            date_iso = _parse_date(text)
        if not date_iso:
            continue

        url = None
        anchor = row.find("a", href=True)
        if anchor:
            url = anchor["href"]

        usd = cents / 100.0
        if not is_acceptable(title, usd):
            continue

        out.append(
            {
                "source": "130point",
                "title": title,
                "usd_cents": cents,
                "date": date_iso,
                "url": url,
            }
        )

    return out


def fetch(timeout: int = 20) -> list[dict]:
    """Hit 130point's sales endpoint and return parsed, filtered sales.

    Returns an empty list if the page is challenge-gated (Cloudflare) or
    otherwise unparseable. The orchestrator already isolates exceptions, but
    this also defensively swallows non-2xx responses since CF replies 403
    with a JS challenge body.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.8",
    }
    r = requests.get(URL, headers=headers, timeout=timeout)
    if r.status_code != 200:
        return []
    return parse(r.text)


def parse_fixture(path: str | Path) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"))

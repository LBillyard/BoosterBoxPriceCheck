"""eBay UK sold-listings source.

eBay UK serves SRP (Search Results Page) results as static HTML for desktop
user agents. The current layout (April 2026) renders each result as a
``<div class="s-card">`` containing:

* ``.s-card__title`` — listing title (with a trailing "Opens in a new
  window or tab" we strip)
* ``.s-card__price`` — sold price in GBP (e.g. "£41,250.00"); occasionally a
  range like "£40,000.00 to £45,000.00", in which case we use the lower bound
* ``.s-card__caption`` — sold metadata, e.g. "Sold 16 Apr 2026"
* ``a.s-card__link`` — outbound link

Prices are GBP. We convert to USD inside the source using a passed-in FX
rate (USD→GBP); having the source emit ``usd_cents`` keeps the orchestrator
combinator simple — every entry is comparable in one currency before we
filter on the USD price band. The original GBP is preserved as
``gbp_cents`` for the snapshot.
"""
from __future__ import annotations

import re
import datetime as dt
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ._filter import is_acceptable

URL = (
    "https://www.ebay.co.uk/sch/i.html"
    "?_nkw=pokemon+base+set+booster+box+sealed"
    "&LH_Sold=1&LH_Complete=1&_sop=13"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_GBP_RE = re.compile(r"£\s*([\d,]+(?:\.\d{2})?)")
_DATE_RE = re.compile(
    r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)
_PLACEHOLDER_TITLE = re.compile(r"^shop on ebay$", re.I)
_TRAILING_NOISE = re.compile(r"\s*opens in a new window or tab\s*$", re.I)


def _parse_gbp(text: str) -> int | None:
    """Parse "£41,250.00" or "£40,000.00 to £45,000.00" into integer pence.

    For ranges we take the lower bound (conservative).
    """
    if not text:
        return None
    matches = _GBP_RE.findall(text)
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
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _clean_title(text: str) -> str:
    return _TRAILING_NOISE.sub("", text).strip()


def parse(html: str, gbp_per_usd: float) -> list[dict]:
    """Parse eBay UK sold-listings HTML into normalised sale dicts.

    ``gbp_per_usd`` is the USD→GBP rate (e.g. 0.7389) used to convert the
    GBP price to USD for filter comparison and snapshot consistency.

    Returns items shaped::

        {"source": "ebay_uk", "title": str, "usd_cents": int,
         "gbp_cents": int, "date": "YYYY-MM-DD" | None, "url": str | None}
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

        # GBP -> USD: usd = gbp / (gbp_per_usd)
        usd = (gbp_cents / 100.0) / gbp_per_usd
        usd_cents = int(round(usd * 100))

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
                "source": "ebay_uk",
                "title": title,
                "usd_cents": usd_cents,
                "gbp_cents": gbp_cents,
                "date": date_iso,
                "url": url,
            }
        )

    return out


def fetch(gbp_per_usd: float, timeout: int = 30) -> list[dict]:
    """Hit eBay UK's sold-listings page and return parsed, filtered sales.

    Returns an empty list on non-2xx (eBay occasionally rate-limits with a
    302 to a captcha; the orchestrator wraps this in try/except anyway).
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    r = requests.get(URL, headers=headers, timeout=timeout)
    if r.status_code != 200:
        return []
    r.encoding = "utf-8"
    return parse(r.text, gbp_per_usd)


def parse_fixture(path: str | Path, gbp_per_usd: float) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"), gbp_per_usd)

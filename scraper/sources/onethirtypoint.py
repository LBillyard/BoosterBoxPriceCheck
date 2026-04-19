"""130point.com sold-sales source.

130point.com is a sales aggregator that surfaces eBay/PWCC sold rows. The
public ``/sales/`` page renders results in a table; each row has a title
cell, a USD price cell, a sold-date cell, and (usually) an outbound link
back to the original listing.

NOTE on Cloudflare and the new 130point UI:

130point.com sits behind a Cloudflare managed challenge ("Just a
moment..." interstitial). With **patchright** (a stealth-patched
Playwright fork) the Turnstile challenge does clear in headless-shell
mode after a few seconds — so the CF problem is solved.

However, 130point has *also* been redesigned: the legacy
``/sales/?search=...`` endpoint that used to render a results table now
307-redirects to ``/sales`` and then to the homepage, throwing away the
search query entirely. The new ``/search?q=...`` endpoint loads but
ignores the query-string and shows a placeholder ("Try searching for a
collectible! Enter a search term in the header"); results only appear
after typing into the header search input and submitting client-side.

Wiring up the typed-search flow with patchright would work, but is
brittle (a header DOM tweak breaks the scraper) and slow (~30s per
fetch on top of the existing budget). Until 130point exposes URL-driven
search again — or a small typed-input flow becomes worth the
maintenance cost — ``fetch()`` returns ``[]`` in practice. The
orchestrator records ``130point=0`` and the snapshot still lands with
eBay UK + US data.

The parser is deliberately permissive about row markup — it scans every
``<tr>`` looking for a price-shaped cell, a date-shaped cell, and a link
or title text. That keeps it ready for the day a real table reaches it.

"""
from __future__ import annotations

import re
import datetime as dt
from pathlib import Path

from bs4 import BeautifulSoup

from ._browser import render
from ._filter import is_acceptable

# Search query: "base set booster box sealed" surfaces the most Unlimited
# rows. "unlimited" as a literal word is rare in titles; sellers usually
# default to no edition keyword for Unlimited stock. Sorted newest-first.
URL = "https://130point.com/sales/?search=base+set+booster+box+sealed&sort=date"

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


def fetch(timeout_ms: int = 30000) -> list[dict]:
    """Hit 130point's sales endpoint via patchright-driven Chromium.

    The page is Cloudflare-protected, so we render through patchright
    (stealth-patched Playwright). Cloudflare's Turnstile usually clears
    within ~5-10s in patchright; we then wait up to 20s for ``table tr``
    markup to appear. As of the module docstring's note, the legacy
    ``/sales/`` URL now redirects to the homepage and the wait will time
    out — :func:`parse` returns ``[]`` and the orchestrator carries on.
    The render() call is kept in place so the source resumes returning
    data the moment 130point restores URL-driven search.
    """
    try:
        html = render(
            URL,
            wait_selector="table tr",
            timeout_ms=timeout_ms,
            selector_timeout_ms=20000,
        )
    except Exception:
        return []
    return parse(html)


def parse_fixture(path: str | Path) -> list[dict]:
    """Convenience for tests: parse a saved HTML file."""
    return parse(Path(path).read_text(encoding="utf-8"))

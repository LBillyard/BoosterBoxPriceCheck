from bs4 import BeautifulSoup
from datetime import datetime
import re

PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{2})?)")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_FORMATS = ("%Y-%m-%d", "%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%m/%d/%Y")

# Minimum plausible price (in cents) for a sealed Pokemon booster box.
# Anything below this is treated as noise/placeholder (e.g. $0.00 change spans
# or stale fields PriceCharting reuses for grade columns on sealed product).
_MIN_PLAUSIBLE_CENTS = 100_000


def _to_cents(price_text: str) -> int | None:
    m = PRICE_RE.search(price_text)
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", "")) * 100))


def parse_prices(html: str) -> dict[str, int]:
    """Extract current prices per condition from a PriceCharting product page.

    Returns dict like {"loose": 3622857, ...} where values are integer cents
    (USD). Only conditions with a plausible current price are included; cells
    rendered as "-" or with implausibly low values are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    prices: dict[str, int] = {}

    # PriceCharting wraps each current price in a <td id="..._price"> in the
    # main price_data table. The first descendant span.price.js-price holds
    # the displayed current value (a sibling .change span holds the delta and
    # must be ignored).
    for table_id, label in [
        ("used_price", "loose"),
        ("complete_price", "cib"),
        ("new_price", "new"),
        ("graded_price", "sealed"),
        ("box_only_price", "box_only"),
        ("manual_only_price", "manual_only"),
    ]:
        cell = soup.find(id=table_id)
        if not cell:
            continue
        main = cell.find("span", class_="price")
        if not main:
            continue
        cents = _to_cents(main.get_text(" ", strip=True))
        if cents is None or cents < _MIN_PLAUSIBLE_CENTS:
            continue
        prices[label] = cents
    return prices


def _normalise_date(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    if _ISO_DATE_RE.match(text):
        return text
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_last_sold(html: str) -> dict | None:
    """Find the most recent recorded sale on the page.

    Returns {"usd_cents": int, "date": "YYYY-MM-DD"} or None.

    PriceCharting renders completed sales in a ``<table class="hoverable-rows
    sortable">`` whose rows contain a ``<td class="date">`` and a
    ``<span class="js-price">`` price. The table defaults to descending date
    order, but to be robust we scan all rows and return the latest.
    """
    soup = BeautifulSoup(html, "html.parser")

    best_date: str | None = None
    best_cents: int | None = None

    for row in soup.find_all("tr"):
        date_cell = row.find("td", class_="date")
        if not date_cell:
            continue
        iso_date = _normalise_date(date_cell.get_text(" ", strip=True))
        if not iso_date:
            continue
        price_span = row.find("span", class_="js-price")
        if not price_span:
            continue
        cents = _to_cents(price_span.get_text(" ", strip=True))
        if cents is None or cents < _MIN_PLAUSIBLE_CENTS:
            continue
        if best_date is None or iso_date > best_date:
            best_date = iso_date
            best_cents = cents

    if best_date is None or best_cents is None:
        return None
    return {"usd_cents": best_cents, "date": best_date}


# Map a condition-comparison table header (e.g. "Loose Price", "CIB Price",
# "New Price", "Graded Price") to the canonical short label used elsewhere in
# this module / the storage layer. Anything unrecognised falls through as the
# raw header text (lower-cased, " price" suffix stripped).
_CONDITION_HEADER_MAP = {
    "loose price": "loose",
    "cib price": "cib",
    "complete price": "cib",
    "new price": "new",
    "sealed price": "sealed",
    "graded price": "sealed",
    "box only price": "box_only",
    "manual only price": "manual_only",
}


def _normalise_condition_header(text: str) -> str:
    key = text.strip().lower()
    if key in _CONDITION_HEADER_MAP:
        return _CONDITION_HEADER_MAP[key]
    if key.endswith(" price"):
        key = key[: -len(" price")]
    return key.strip().replace(" ", "_") or "unknown"


def parse_listings(html: str) -> list[dict]:
    """Extract active marketplace listings (eBay etc.) shown on the page.

    Returns a list of {"usd_cents": int, "condition": str, "seller": str|None,
    "url": str|None}. May be empty.

    PriceCharting renders active store offers in one or more
    ``<table class="condition-comparison">`` blocks, one per condition. Each
    body row carries ``data-source-name="eBay"`` (or TCGPlayer / PriceCharting
    / Amazon / etc.) plus a ``<td class="price">`` and a ``<td class="see-it">``
    that wraps an outbound affiliate link. Rows whose price cell is empty
    (no current offer) are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    listings: list[dict] = []

    for table in soup.find_all("table", class_="condition-comparison"):
        header_cell = table.find("th", class_="condition")
        condition = (
            _normalise_condition_header(header_cell.get_text(" ", strip=True))
            if header_cell
            else "unknown"
        )

        for row in table.find_all("tr"):
            seller = row.get("data-source-name")
            if not seller:
                continue

            price_cell = row.find("td", class_="price")
            if not price_cell:
                continue
            cents = _to_cents(price_cell.get_text(" ", strip=True))
            if cents is None or cents < _MIN_PLAUSIBLE_CENTS:
                continue

            url: str | None = None
            see_it = row.find("td", class_="see-it")
            if see_it:
                anchor = see_it.find("a", href=True)
                if anchor:
                    url = anchor["href"]

            listings.append(
                {
                    "usd_cents": cents,
                    "condition": condition,
                    "seller": seller or None,
                    "url": url,
                }
            )

    return listings

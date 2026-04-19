from bs4 import BeautifulSoup
import re

PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{2})?)")

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

PURCHASE_PRICE_GBP = 29253.05

# Cap on how many recent_sales entries we persist into the snapshot. The
# frontend only renders the top ~10, but keeping a few more in JSON gives us
# headroom (and history when sources are slow).
RECENT_SALES_CAP = 25

# Cap on currently-active listings. There's no point shipping more than the
# UI will render, and the snapshot file size matters for GitHub Pages.
ACTIVE_LISTINGS_CAP = 25


def _cents_to_dollars(cents: int) -> float:
    return round(cents / 100, 2)

def _convert(usd: float, fx: float) -> float:
    return round(usd * fx, 2)


def _normalise_sale(item: dict, fx: float) -> dict:
    """Project a source-level sale dict into the snapshot's recent_sales shape.

    Each source emits at minimum: source, title, usd_cents, date, url.
    eBay UK additionally emits gbp_cents (its native currency); for other
    sources we derive GBP from USD via the FX rate.
    """
    usd = _cents_to_dollars(item["usd_cents"])
    if "gbp_cents" in item and item["gbp_cents"]:
        gbp = _cents_to_dollars(item["gbp_cents"])
    else:
        gbp = _convert(usd, fx)
    return {
        "source": item["source"],
        "title": item["title"],
        "usd": usd,
        "gbp": gbp,
        "date": item.get("date"),
        "url": item.get("url"),
    }


def _sort_and_cap(sales: list[dict], cap: int) -> list[dict]:
    """Sort by date descending (None dates last) and cap to ``cap`` rows."""
    def key(s):
        # ISO YYYY-MM-DD sorts lexicographically. Items with no date get
        # the empty string and fall to the end.
        return s.get("date") or ""
    sales_sorted = sorted(sales, key=key, reverse=True)
    return sales_sorted[:cap]


def _normalise_active(item: dict, fx: float) -> dict:
    """Project an active-listing source dict into the snapshot shape.

    Active listings have no sale date (they're currently for sale). They
    follow the same usd_cents / optional gbp_cents convention as sold rows.
    """
    usd = _cents_to_dollars(item["usd_cents"])
    if "gbp_cents" in item and item["gbp_cents"]:
        gbp = _cents_to_dollars(item["gbp_cents"])
    else:
        gbp = _convert(usd, fx)
    return {
        "source": item["source"],
        "title": item["title"],
        "usd": usd,
        "gbp": gbp,
        "url": item.get("url"),
    }


def _sort_active_asc(items: list[dict], cap: int) -> list[dict]:
    """Sort active listings by ask price (USD) ascending, cap to ``cap``."""
    return sorted(items, key=lambda x: x.get("usd") or 0)[:cap]


def build_snapshot(prices, last_sold, listings, fx, scraped_at: str,
                   recent_sales: list[dict] | None = None,
                   active_listings: list[dict] | None = None) -> dict:
    out_prices = {}
    for cond, cents in prices.items():
        usd = _cents_to_dollars(cents)
        out_prices[cond] = {"usd": usd, "gbp": _convert(usd, fx)}

    out_last_sold = None
    if last_sold:
        usd = _cents_to_dollars(last_sold["usd_cents"])
        out_last_sold = {"usd": usd, "gbp": _convert(usd, fx), "date": last_sold["date"]}

    out_listings = []
    for item in listings:
        usd = _cents_to_dollars(item["usd_cents"])
        out_listings.append({
            "condition": item["condition"],
            "usd": usd,
            "gbp": _convert(usd, fx),
            "seller": item.get("seller"),
            "url": item.get("url"),
        })

    out_recent_sales: list[dict] = []
    if recent_sales:
        out_recent_sales = _sort_and_cap(
            [_normalise_sale(s, fx) for s in recent_sales],
            RECENT_SALES_CAP,
        )

    out_active: list[dict] = []
    if active_listings:
        out_active = _sort_active_asc(
            [_normalise_active(a, fx) for a in active_listings],
            ACTIVE_LISTINGS_CAP,
        )

    return {
        "scraped_at": scraped_at,
        "fx": {"usd_to_gbp": fx, "fetched_at": scraped_at},
        "prices": out_prices,
        "last_sold": out_last_sold,
        "listings": out_listings,
        "recent_sales": out_recent_sales,
        "active_listings": out_active,
        "purchase_price_gbp": PURCHASE_PRICE_GBP,
    }

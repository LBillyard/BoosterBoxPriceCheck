PURCHASE_PRICE_GBP = 29253.05

def _cents_to_dollars(cents: int) -> float:
    return round(cents / 100, 2)

def _convert(usd: float, fx: float) -> float:
    return round(usd * fx, 2)

def build_snapshot(prices, last_sold, listings, fx, scraped_at: str) -> dict:
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

    return {
        "scraped_at": scraped_at,
        "fx": {"usd_to_gbp": fx, "fetched_at": scraped_at},
        "prices": out_prices,
        "last_sold": out_last_sold,
        "listings": out_listings,
        "purchase_price_gbp": PURCHASE_PRICE_GBP,
    }

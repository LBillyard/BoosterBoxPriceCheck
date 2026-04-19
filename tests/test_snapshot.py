from scraper.snapshot import build_snapshot

def test_build_snapshot_converts_currencies_and_includes_purchase_price():
    prices = {"loose": 3642000, "new": 3680000}
    last_sold = {"usd_cents": 3575000, "date": "2026-04-17"}
    listings = [{"usd_cents": 3460000, "condition": "Sealed", "seller": None, "url": None}]
    fx = 0.80
    snap = build_snapshot(prices, last_sold, listings, fx, scraped_at="2026-04-19T12:00:00Z")

    assert snap["fx"]["usd_to_gbp"] == 0.80
    assert snap["prices"]["loose"]["usd"] == 36420
    assert snap["prices"]["loose"]["gbp"] == round(36420 * 0.80, 2)
    assert snap["last_sold"]["gbp"] == round(35750 * 0.80, 2)
    assert snap["listings"][0]["gbp"] == round(34600 * 0.80, 2)
    assert snap["purchase_price_gbp"] == 29253.05

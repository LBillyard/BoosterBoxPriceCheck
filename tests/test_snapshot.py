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
    # New field present even when no sales passed.
    assert snap["recent_sales"] == []


def test_build_snapshot_includes_recent_sales_sorted_desc():
    fx = 0.80
    sales = [
        {"source": "130point", "title": "Pokemon Base Set Booster Box Sealed",
         "usd_cents": 4_000_000, "date": "2026-04-10", "url": "https://x"},
        {"source": "ebay_uk", "title": "Pokemon Base Set Booster Box Unlimited Sealed",
         "usd_cents": 4_300_000, "gbp_cents": 3_180_000,
         "date": "2026-04-15", "url": "https://y"},
        {"source": "130point", "title": "Pokemon Base Set Booster Box Sealed Heavy",
         "usd_cents": 3_900_000, "date": None, "url": None},
    ]
    snap = build_snapshot({}, None, [], fx, scraped_at="2026-04-19T12:00:00Z",
                          recent_sales=sales)

    rs = snap["recent_sales"]
    assert len(rs) == 3
    # Sorted by date desc, None last.
    assert rs[0]["date"] == "2026-04-15"
    assert rs[1]["date"] == "2026-04-10"
    assert rs[2]["date"] is None

    # eBay UK row uses its native gbp_cents.
    ebay = rs[0]
    assert ebay["source"] == "ebay_uk"
    assert ebay["usd"] == 43_000.0
    assert ebay["gbp"] == 31_800.0  # from gbp_cents, not from FX

    # 130point row converts USD -> GBP via FX.
    pt = rs[1]
    assert pt["source"] == "130point"
    assert pt["usd"] == 40_000.0
    assert pt["gbp"] == round(40_000 * 0.80, 2)


def test_build_snapshot_caps_recent_sales_at_25():
    sales = [
        {"source": "ebay_uk", "title": f"Pokemon Base Set Booster Box Sealed #{i}",
         "usd_cents": 4_000_000 + i, "gbp_cents": 3_000_000,
         "date": f"2026-04-{(i % 28) + 1:02d}", "url": None}
        for i in range(40)
    ]
    snap = build_snapshot({}, None, [], 0.80, scraped_at="2026-04-19T12:00:00Z",
                          recent_sales=sales)
    assert len(snap["recent_sales"]) == 25

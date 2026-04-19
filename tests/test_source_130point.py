from pathlib import Path

from scraper.sources.onethirtypoint import parse_fixture

FIXTURE = Path(__file__).parent / "fixtures" / "130point.html"


def test_parse_filters_to_unlimited_only():
    sales = parse_fixture(FIXTURE)
    titles = [s["title"] for s in sales]
    # Three rows in the fixture pass the filter:
    #   * "...Unlimited Booster Box Sealed..."
    #   * "...Booster Box Sealed (Unlimited)..."
    #   * "...Base Set Booster Box Sealed Heavy" (no edition keyword, in band)
    assert len(sales) == 3, f"expected 3, got {len(sales)}: {titles}"

    for t in titles:
        assert "1st Edition" not in t
        assert "Shadowless" not in t
        assert "Jungle" not in t
        assert "Booster Pack" not in t


def test_parse_extracts_canonical_shape():
    sales = parse_fixture(FIXTURE)
    s = sales[0]
    assert s["source"] == "130point"
    assert isinstance(s["title"], str) and s["title"]
    assert isinstance(s["usd_cents"], int) and s["usd_cents"] > 0
    assert s["date"] and len(s["date"]) == 10  # YYYY-MM-DD
    assert s["url"] is None or s["url"].startswith("http")


def test_parse_first_record_is_top_unlimited_sale():
    sales = parse_fixture(FIXTURE)
    s = sales[0]
    assert "Unlimited" in s["title"]
    assert s["usd_cents"] == 4_125_000
    assert s["date"] == "2026-04-15"
    assert s["url"] == "https://www.ebay.com/itm/111222333"


def test_parse_handles_us_date_format():
    sales = parse_fixture(FIXTURE)
    iso_dates = {s["date"] for s in sales}
    # Includes both ISO and 04/12/2026 → 2026-04-12
    assert "2026-04-12" in iso_dates

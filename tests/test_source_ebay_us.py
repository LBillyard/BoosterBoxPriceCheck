from pathlib import Path

from scraper.sources.ebay_us import parse_fixture

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "ebay_us.html"


def test_real_fixture_returns_at_least_one_unlimited():
    """The real eBay US capture (saved 2026-04 from the live SRP) contains
    at least one acceptable Unlimited Base Set Booster Box sale.

    If this ever fails it means either:
      1. The eBay SRP markup changed (selector mismatch), or
      2. There were no Unlimited boxes in the most recent ~60 sold rows
         for the chosen query — re-capture the fixture and re-check.
    """
    res = parse_fixture(REAL_FIXTURE)
    assert len(res) >= 1, (
        "expected at least one Unlimited Base Set Booster Box sale; "
        "got 0. Either the filter is over-strict, the fixture is stale, "
        "or eBay's markup moved."
    )


def test_real_fixture_filters_garbage():
    """Whatever passes the filter must look like the real product."""
    res = parse_fixture(REAL_FIXTURE)
    for r in res:
        assert r["source"] == "ebay_us"
        assert "1st Edition" not in r["title"]
        assert "1st Ed" not in r["title"]
        assert "Shadowless" not in r["title"]
        assert "Base Set 2" not in r["title"]
        assert "Mega Evolution" not in r["title"]
        # Price band sanity (USD).
        assert 15_000 <= r["usd_cents"] / 100 <= 80_000
        assert r["title"]
        assert r["url"] is None or r["url"].startswith("http")


def test_parser_strips_new_listing_prefix():
    """eBay sometimes prefixes titles with "New Listing"; strip it."""
    from scraper.sources.ebay_us import _clean_title
    assert _clean_title(
        "New Listing Pokemon Base Set Unlimited Booster Box "
        "Opens in a new window or tab"
    ) == "Pokemon Base Set Unlimited Booster Box"


def test_parser_handles_us_date_format():
    """US dates look like 'Sold  Mar 10, 2026' — confirm parsing."""
    from scraper.sources.ebay_us import _parse_date
    assert _parse_date("Sold  Mar 10, 2026") == "2026-03-10"
    assert _parse_date("Sold March 10, 2026") == "2026-03-10"
    assert _parse_date("nothing here") is None


def test_parser_handles_price_range():
    """Range like '$30,000.00 to $35,000.00' takes the lower bound."""
    from scraper.sources.ebay_us import _parse_usd
    assert _parse_usd("$30,000.00 to $35,000.00") == 30_000_00
    assert _parse_usd("$36,600.00") == 36_600_00
    assert _parse_usd("free") is None

"""Active-listing scraper tests reuse the existing eBay UK / US fixtures.

The DOM is the same SRP as the sold pages (eBay ships the same React
component), so the parser must succeed on the same fixture HTML — just
emitting items with ``date is None`` and the correct module wiring.
"""
from pathlib import Path

from scraper.sources import ebay_uk_active, ebay_us_active

FIX_DIR = Path(__file__).parent / "fixtures"
GBP_PER_USD = 0.7389


def test_ebay_uk_active_parses_synthetic_fixture():
    res = ebay_uk_active.parse_fixture(FIX_DIR / "ebay_uk_synthetic.html",
                                        GBP_PER_USD)
    assert len(res) == 3
    for r in res:
        assert r["source"] == "ebay_uk"
        assert r["date"] is None
        assert r["gbp_cents"] > 0
        assert r["usd_cents"] > 0


def test_ebay_us_active_parses_real_fixture_with_no_dates():
    res = ebay_us_active.parse_fixture(FIX_DIR / "ebay_us.html")
    assert len(res) >= 1
    for r in res:
        assert r["source"] == "ebay_us"
        assert r["date"] is None
        assert 15_000 <= r["usd_cents"] / 100 <= 80_000


def test_ebay_uk_active_filters_garbage():
    res = ebay_uk_active.parse_fixture(FIX_DIR / "ebay_uk.html",
                                        GBP_PER_USD)
    for r in res:
        assert "1st Edition" not in r["title"]
        assert "Shadowless" not in r["title"]
        assert 15_000 <= r["usd_cents"] / 100 <= 80_000
        assert r["date"] is None

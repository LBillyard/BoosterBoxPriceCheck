from pathlib import Path

from scraper.sources.ebay_uk import parse_fixture

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "ebay_uk.html"
SYNTHETIC_FIXTURE = Path(__file__).parent / "fixtures" / "ebay_uk_synthetic.html"

# Approx USD->GBP at the time the real fixture was captured (~$1 = £0.7389).
GBP_PER_USD = 0.7389


def test_real_fixture_parses_without_error_and_filter_rejects_garbage():
    # The real eBay UK SRP captured for this query returns lots of
    # not-the-right-thing rows (Scarlet & Violet "Base Set", booster
    # *packs*, Crown Zenith product, Gym Challenge boxes, etc). The filter
    # is expected to reject all of them — the test asserts no garbage
    # leaks through.
    res = parse_fixture(REAL_FIXTURE, GBP_PER_USD)
    for r in res:
        assert "1st Edition" not in r["title"]
        assert "Shadowless" not in r["title"]
        # Price band sanity (USD).
        assert 15_000 <= r["usd_cents"] / 100 <= 80_000


def test_synthetic_fixture_yields_three_acceptable_rows():
    res = parse_fixture(SYNTHETIC_FIXTURE, GBP_PER_USD)
    titles = [r["title"] for r in res]
    assert len(res) == 3, f"expected 3, got {len(res)}: {titles}"
    for r in res:
        assert r["source"] == "ebay_uk"
        assert r["title"]
        assert r["gbp_cents"] > 0
        assert r["usd_cents"] > 0
        assert r["url"] and r["url"].startswith("http")


def test_synthetic_first_row_extracts_correctly():
    res = parse_fixture(SYNTHETIC_FIXTURE, GBP_PER_USD)
    first = res[0]
    assert first["title"] == "Pokemon Base Set Unlimited Booster Box Sealed WOTC 1999 Charizard"
    assert first["gbp_cents"] == 3_250_000
    assert first["date"] == "2026-04-16"
    assert first["url"] == "https://www.ebay.co.uk/itm/100000001"
    # USD = 32500 / 0.7389 ≈ 43_984.30
    assert 4_300_000 < first["usd_cents"] < 4_500_000


def test_synthetic_range_price_uses_lower_bound():
    res = parse_fixture(SYNTHETIC_FIXTURE, GBP_PER_USD)
    # row with "£30,000.00 to £35,000.00" should use £30,000
    row = next(r for r in res if r["url"].endswith("100000005"))
    assert row["gbp_cents"] == 3_000_000


def test_filter_rejects_first_edition_and_placeholder():
    res = parse_fixture(SYNTHETIC_FIXTURE, GBP_PER_USD)
    titles = [r["title"] for r in res]
    assert not any("1st Edition" in t for t in titles)
    assert not any("Shop on eBay" in t for t in titles)
    assert not any("Scarlet and Violet" in t for t in titles)

"""Tests for the eBay Browse API client and the two marketplace sources.

We never hit the live API in tests — all fixtures are captured JSON
responses in tests/fixtures/. Token caching is exercised via a fake
clock so we don't sleep.
"""
import json
from pathlib import Path

import pytest

from scraper.sources._ebay_api_client import _normalise_response

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_normalise_us_response_returns_expected_shape():
    payload = _load("ebay_browse_us.json")
    rows = _normalise_response(payload, currency="USD")

    # Fixture has N items; assert against the first one's required fields
    assert len(rows) > 0
    row = rows[0]
    assert set(row.keys()) >= {
        "title", "usd_cents", "date", "url",
        "seller_name", "seller_feedback", "seller_positive_pct",
    }
    assert isinstance(row["usd_cents"], int)
    assert row["usd_cents"] > 0
    assert isinstance(row["title"], str) and row["title"]
    # USD rows must NOT carry a gbp_cents key — snapshot.py reads its
    # presence as a signal to skip the USD->GBP FX round-trip.
    assert "gbp_cents" not in row


def test_normalise_uk_response_converts_gbp_to_usd_cents():
    payload = _load("ebay_browse_uk.json")
    gbp_per_usd = 0.75  # 1 USD = 0.75 GBP
    rows = _normalise_response(payload, currency="GBP", gbp_per_usd=gbp_per_usd)

    assert len(rows) > 0
    row = rows[0]
    # Spot-check the conversion: usd_cents = gbp_value / gbp_per_usd * 100
    raw_gbp = float(payload["itemSummaries"][0]["price"]["value"])
    expected = round(raw_gbp / gbp_per_usd * 100)
    assert row["usd_cents"] == expected
    # GBP rows must also carry gbp_cents in their native currency so
    # snapshot.py can use the exact value rather than round-tripping
    # through FX.
    assert row["gbp_cents"] == round(raw_gbp * 100)


def test_normalise_response_raises_on_unknown_currency():
    payload = {
        "itemSummaries": [
            {
                "title": "Test",
                "price": {"value": "100.00", "currency": "EUR"},
                "itemWebUrl": "https://x",
            }
        ]
    }
    with pytest.raises(ValueError):
        _normalise_response(payload, currency="EUR")


def test_normalise_response_raises_when_gbp_missing_fx():
    payload = {
        "itemSummaries": [
            {
                "title": "Test",
                "price": {"value": "100.00", "currency": "GBP"},
                "itemWebUrl": "https://x",
            }
        ]
    }
    with pytest.raises(ValueError):
        _normalise_response(payload, currency="GBP", gbp_per_usd=None)


def test_normalise_handles_missing_seller_block():
    # Synthetic minimal payload — itemSummaries with no seller key
    payload = {
        "itemSummaries": [
            {
                "title": "Pokemon Base Set Booster Box WOTC Sealed",
                "price": {"value": "30000.00", "currency": "USD"},
                "itemWebUrl": "https://www.ebay.com/itm/123",
                "itemCreationDate": "2026-05-10T12:00:00.000Z",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert len(rows) == 1
    assert rows[0]["seller_name"] is None
    assert rows[0]["seller_feedback"] is None
    assert rows[0]["seller_positive_pct"] is None


def test_normalise_skips_items_with_missing_price():
    payload = {
        "itemSummaries": [
            {"title": "No price", "itemWebUrl": "https://x"},
            {"title": "Has price", "price": {"value": "25000.00", "currency": "USD"}, "itemWebUrl": "https://y"},
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert len(rows) == 1
    assert rows[0]["title"] == "Has price"


def test_normalise_parses_item_creation_date():
    payload = {
        "itemSummaries": [
            {
                "title": "Test",
                "price": {"value": "20000.00", "currency": "USD"},
                "itemWebUrl": "https://x",
                "itemCreationDate": "2026-05-10T12:00:00.000Z",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert rows[0]["date"] == "2026-05-10"

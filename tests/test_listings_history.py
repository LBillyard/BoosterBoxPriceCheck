"""Tests for scraper.listings_history.

Mirrors the style of test_history.py — fixture-free, table-driven where
sensible, no network. Time is injected so we can assert exact timestamps.
"""
import datetime as dt
import json
from pathlib import Path

import pytest

from scraper.listings_history import merge_listings


def _row(item_id="v1|111|0", usd_cents=3_500_000, source="ebay_api_us",
         title="Pokemon Base Set Booster Box WOTC Sealed",
         url=None, gbp_cents=None,
         seller_name="seller_a", seller_feedback=100, seller_positive_pct=99.5):
    out = {
        "item_id": item_id,
        "source": source,
        "title": title,
        "usd_cents": usd_cents,
        "url": url or f"https://www.ebay.com/itm/{item_id.split('|')[1]}",
        "seller_name": seller_name,
        "seller_feedback": seller_feedback,
        "seller_positive_pct": seller_positive_pct,
    }
    if gbp_cents is not None:
        out["gbp_cents"] = gbp_cents
    return out


_NOW1 = dt.datetime(2026, 5, 17, 14, 0, 0, tzinfo=dt.timezone.utc)
_NOW2 = dt.datetime(2026, 5, 17, 22, 0, 0, tzinfo=dt.timezone.utc)
_NOW3 = dt.datetime(2026, 5, 18, 10, 0, 0, tzinfo=dt.timezone.utc)


def test_first_run_writes_all_rows_with_first_and_last_seen_equal(tmp_path):
    path = tmp_path / "h.json"
    rows = [_row(item_id="v1|111|0"), _row(item_id="v1|222|0", usd_cents=4_800_000)]
    merge_listings(rows, path, now=_NOW1)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 2
    for e in saved:
        assert e["first_seen"] == "2026-05-17T14:00:00Z"
        assert e["last_seen"] == "2026-05-17T14:00:00Z"


def test_same_item_same_price_updates_last_seen_only(tmp_path):
    path = tmp_path / "h.json"
    merge_listings([_row()], path, now=_NOW1)
    merge_listings([_row()], path, now=_NOW2)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["first_seen"] == "2026-05-17T14:00:00Z"
    assert saved[0]["last_seen"] == "2026-05-17T22:00:00Z"


def test_same_item_different_price_creates_new_entry(tmp_path):
    path = tmp_path / "h.json"
    merge_listings([_row(usd_cents=5_000_000)], path, now=_NOW1)
    merge_listings([_row(usd_cents=4_500_000)], path, now=_NOW2)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 2
    prices = sorted(e["usd_cents"] for e in saved)
    assert prices == [4_500_000, 5_000_000]
    # Cheaper (newer) entry has the newer first_seen
    cheap = next(e for e in saved if e["usd_cents"] == 4_500_000)
    assert cheap["first_seen"] == "2026-05-17T22:00:00Z"


def test_row_missing_item_id_is_skipped(tmp_path):
    path = tmp_path / "h.json"
    rows = [_row(), {**_row(item_id="v1|999|0"), "item_id": None}]
    merge_listings(rows, path, now=_NOW1)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["item_id"] == "v1|111|0"


def test_row_disappearing_from_active_set_is_not_removed(tmp_path):
    """If we scrape A on day 1 and B on day 2, history must keep both."""
    path = tmp_path / "h.json"
    merge_listings([_row(item_id="v1|111|0")], path, now=_NOW1)
    merge_listings([_row(item_id="v1|222|0", usd_cents=4_800_000)], path, now=_NOW2)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 2
    # Day-1 entry's last_seen wasn't touched on day 2
    e1 = next(e for e in saved if e["item_id"] == "v1|111|0")
    assert e1["last_seen"] == "2026-05-17T14:00:00Z"


def test_gbp_cents_preserved_for_uk_rows(tmp_path):
    path = tmp_path / "h.json"
    rows = [_row(source="ebay_api_uk", gbp_cents=2_500_000)]
    merge_listings(rows, path, now=_NOW1)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[0]["gbp_cents"] == 2_500_000


def test_existing_entry_does_not_refresh_seller_fields(tmp_path):
    """An existing (item_id, price) keeps its first-observed seller data
    even if a later scrape shows different (higher) feedback. This keeps
    each entry deterministic per dedup key."""
    path = tmp_path / "h.json"
    merge_listings([_row(seller_feedback=100, seller_positive_pct=99.0)], path, now=_NOW1)
    merge_listings([_row(seller_feedback=200, seller_positive_pct=100.0)], path, now=_NOW2)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["seller_feedback"] == 100
    assert saved[0]["seller_positive_pct"] == 99.0


def test_corrupt_history_starts_fresh(tmp_path):
    """A junk JSON file shouldn't crash the scrape — start over."""
    path = tmp_path / "h.json"
    path.write_text("{not json", encoding="utf-8")
    merge_listings([_row()], path, now=_NOW1)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1


def test_returns_full_merged_list_for_logging(tmp_path):
    """The function returns the post-merge list so the orchestrator can log."""
    path = tmp_path / "h.json"
    result = merge_listings([_row(), _row(item_id="v1|222|0", usd_cents=4_800_000)], path, now=_NOW1)
    assert len(result) == 2

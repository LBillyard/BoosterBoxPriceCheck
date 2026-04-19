import datetime as dt
import json
from pathlib import Path

from scraper.history import merge_sales, HISTORY_CAP


def _sale(source="ebay_us", title="Pokemon Base Set Booster Box Sealed",
          usd=42500.0, gbp=31403.0, date="2026-03-29",
          url="https://www.ebay.com/itm/1"):
    return {
        "source": source,
        "title": title,
        "usd": usd,
        "gbp": gbp,
        "date": date,
        "url": url,
    }


def test_first_scrape_creates_history_with_first_seen_at(tmp_path):
    path = tmp_path / "sales_history.json"
    sales = [_sale(url="https://x/1", date="2026-04-10"),
             _sale(url="https://x/2", date="2026-04-15")]
    now = dt.datetime(2026, 4, 19, 16, 58, 22, tzinfo=dt.timezone.utc)
    out = merge_sales(sales, path, now=now)
    assert path.exists()
    assert len(out) == 2
    # Sorted desc by date.
    assert out[0]["date"] == "2026-04-15"
    assert out[1]["date"] == "2026-04-10"
    # All entries got the same first_seen_at.
    for entry in out:
        assert entry["first_seen_at"] == "2026-04-19T16:58:22Z"


def test_second_scrape_appends_new_skips_duplicates(tmp_path):
    path = tmp_path / "sales_history.json"

    # First scrape: two sales.
    first_now = dt.datetime(2026, 4, 19, 12, 0, 0, tzinfo=dt.timezone.utc)
    merge_sales(
        [_sale(url="https://x/1", date="2026-04-10"),
         _sale(url="https://x/2", date="2026-04-15")],
        path, now=first_now,
    )

    # Second scrape: one repeat (URL collides) + one new.
    second_now = dt.datetime(2026, 4, 20, 12, 0, 0, tzinfo=dt.timezone.utc)
    merged = merge_sales(
        [_sale(url="https://x/2", date="2026-04-15"),  # dup
         _sale(url="https://x/3", date="2026-04-18")],  # new
        path, now=second_now,
    )

    # Total of 3 unique sales.
    assert len(merged) == 3
    by_url = {e["url"]: e for e in merged}
    assert by_url["https://x/1"]["first_seen_at"] == "2026-04-19T12:00:00Z"
    assert by_url["https://x/2"]["first_seen_at"] == "2026-04-19T12:00:00Z"
    # Only the genuinely-new row carries the second-scrape timestamp.
    assert by_url["https://x/3"]["first_seen_at"] == "2026-04-20T12:00:00Z"


def test_dedupe_falls_back_to_content_hash_when_url_missing(tmp_path):
    path = tmp_path / "sales_history.json"
    a = _sale(url=None, date="2026-04-10", title="Box A", usd=40000.0)
    b = _sale(url=None, date="2026-04-10", title="Box A", usd=40000.0)  # same content
    c = _sale(url=None, date="2026-04-10", title="Box B", usd=41000.0)  # diff
    merged = merge_sales([a, b, c], path)
    assert len(merged) == 2
    titles = sorted(e["title"] for e in merged)
    assert titles == ["Box A", "Box B"]


def test_history_caps_at_limit(tmp_path):
    path = tmp_path / "sales_history.json"
    sales = [
        _sale(url=f"https://x/{i}", date=f"2026-01-{(i % 28) + 1:02d}", usd=40000.0 + i)
        for i in range(HISTORY_CAP + 50)
    ]
    merged = merge_sales(sales, path)
    assert len(merged) == HISTORY_CAP


def test_history_file_contents_are_valid_json(tmp_path):
    path = tmp_path / "sales_history.json"
    merge_sales([_sale()], path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert raw[0]["url"] == "https://www.ebay.com/itm/1"

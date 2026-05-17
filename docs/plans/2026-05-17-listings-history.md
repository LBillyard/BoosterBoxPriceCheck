# Listings History Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `data/listings_history.json` — a persistent, deduped-by-`(item_id, usd_cents)` record of every API-sourced active listing we observe, updated each cron run.

**Architecture:** New module `scraper/listings_history.py` mirroring `scraper.history`'s shape. Modifies `_ebay_api_client._normalise_response` to emit `item_id`. Wires a `merge_listings(active_rows, LISTINGS_HISTORY_FILE)` call into `scraper.scrape` after the snapshot build.

**Tech Stack:** Python 3.11+, `requests`, `pytest`. No new dependencies.

**Reference design:** [docs/plans/2026-05-17-listings-history-design.md](2026-05-17-listings-history-design.md)

---

## Task 1: Capture `item_id` in the API client (TDD)

**Files:**
- Test: `tests/test_source_ebay_api.py` (extend)
- Modify: `scraper/sources/_ebay_api_client.py`

**Step 1: Write the failing test**

Append to `tests/test_source_ebay_api.py`:

```python
def test_normalise_response_includes_item_id():
    payload = {
        "itemSummaries": [
            {
                "itemId": "v1|115678901234|0",
                "title": "Pokemon Base Set Booster Box WOTC Sealed",
                "price": {"value": "30000.00", "currency": "USD"},
                "itemWebUrl": "https://www.ebay.com/itm/115678901234",
                "itemCreationDate": "2026-05-10T12:00:00.000Z",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert rows[0]["item_id"] == "v1|115678901234|0"


def test_normalise_response_handles_missing_item_id():
    """eBay always returns itemId in real responses, but be defensive."""
    payload = {
        "itemSummaries": [
            {
                "title": "Pokemon Base Set Booster Box",
                "price": {"value": "30000.00", "currency": "USD"},
                "itemWebUrl": "https://www.ebay.com/itm/x",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    # Row still produced (no skip), item_id is None
    assert len(rows) == 1
    assert rows[0].get("item_id") is None
```

**Step 2: Run tests to confirm failure**

```
python -m pytest tests/test_source_ebay_api.py::test_normalise_response_includes_item_id -v
```

Expected: FAIL with `KeyError: 'item_id'` or similar (the field isn't being emitted yet).

**Step 3: Modify `_normalise_response`**

In `scraper/sources/_ebay_api_client.py`, in the row-construction block, add `"item_id": item.get("itemId")` as a new dict key. Place it before `title` so the dict reads top-to-bottom in a sensible identity-first order:

```python
row = {
    "item_id": item.get("itemId"),
    "title": (item.get("title") or "").strip(),
    "usd_cents": usd_cents,
    ...
}
```

**Step 4: Run all eBay-API tests**

```
python -m pytest tests/test_source_ebay_api.py -v
```

Expected: all 16 tests pass (14 prior + 2 new).

**Step 5: Commit**

```bash
git add tests/test_source_ebay_api.py scraper/sources/_ebay_api_client.py
git commit -m "feat: capture item_id from eBay Browse API responses"
```

---

## Task 2: Build the listings_history module (TDD)

**Files:**
- Create: `tests/test_listings_history.py`
- Create: `scraper/listings_history.py`

**Step 1: Write the failing tests**

Create `tests/test_listings_history.py`:

```python
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
```

**Step 2: Run tests to confirm they all fail**

```
python -m pytest tests/test_listings_history.py -v
```

Expected: all 9 tests fail with `ModuleNotFoundError` because `scraper.listings_history` doesn't exist yet.

**Step 3: Implement the module**

Create `scraper/listings_history.py`. Mirror `scraper/history.py`'s style closely:

```python
"""Persistent record of API-sourced active listings.

Background
----------
``data/snapshot.json`` is overwritten on every scrape and the Browse API
only surfaces *currently* active listings. Without persistence we lose
every listing the moment its seller ends, re-prices, or it ages out of
eBay's effective search window.

This module owns ``data/listings_history.json`` — a flat list deduped by
``(item_id, usd_cents)``. Each entry tracks ``first_seen`` (set on
insert) and ``last_seen`` (updated every cron that still sees the row).
A listing that sits at one price is one entry; a listing whose price
drops creates a second entry alongside the first.

Listings that disappear from the active set are NOT removed from history
— their ``last_seen`` stops advancing, which is enough to derive
"ended N days ago" downstream.

Rows missing ``item_id`` are skipped (we can't dedup them).

The file is safe to delete; the next cron rebuilds with whatever is
currently active.

Schema
------
Each entry::

    {
      "item_id": "v1|115678901234|0",
      "source": "ebay_api_us",
      "title": "...",
      "usd_cents": 5000000,
      "gbp_cents": null,          # only present for UK rows
      "url": "https://...",
      "seller_name": "...",
      "seller_feedback": 410,
      "seller_positive_pct": 100.0,
      "first_seen": "2026-05-17T14:00:00Z",
      "last_seen": "2026-05-19T02:00:00Z"
    }
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def _key(row: dict) -> tuple[str, int] | None:
    """Dedup identity: (item_id, usd_cents). None when item_id is absent."""
    item_id = row.get("item_id")
    if not item_id:
        return None
    try:
        usd_cents = int(row["usd_cents"])
    except (KeyError, ValueError, TypeError):
        return None
    return (item_id, usd_cents)


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _iso_z(now: dt.datetime) -> str:
    """UTC ISO8601 with trailing ``Z``, second precision."""
    return (
        now.replace(microsecond=0)
        .astimezone(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def merge_listings(
    active_rows: list[dict],
    history_path: Path,
    *,
    now: dt.datetime | None = None,
) -> list[dict]:
    """Merge currently-active rows into the on-disk history file.

    Behaviour:

    - New ``(item_id, usd_cents)`` combinations are appended with
      ``first_seen == last_seen == now``.
    - Existing combinations get their ``last_seen`` advanced to ``now``.
      Other fields (seller, title, url) keep the values from first
      observation — see design doc.
    - Rows without a usable ``item_id`` or ``usd_cents`` are skipped.
    - Entries in the file that are NOT in ``active_rows`` are left as-is
      (we don't track "ended"; ``last_seen`` is sufficient).

    Returns the post-merge list (so callers can log counts).
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = _iso_z(now)

    existing = _load_existing(history_path)
    # Map dedup-key -> existing entry, for in-place last_seen updates.
    index: dict[tuple[str, int], dict] = {}
    for e in existing:
        k = _key(e)
        if k is not None:
            index[k] = e

    for row in active_rows:
        k = _key(row)
        if k is None:
            continue
        if k in index:
            index[k]["last_seen"] = stamp
            continue
        entry = {
            "item_id": row["item_id"],
            "source": row.get("source"),
            "title": row.get("title"),
            "usd_cents": int(row["usd_cents"]),
            "gbp_cents": row["gbp_cents"] if "gbp_cents" in row else None,
            "url": row.get("url"),
            "seller_name": row.get("seller_name"),
            "seller_feedback": row.get("seller_feedback"),
            "seller_positive_pct": row.get("seller_positive_pct"),
            "first_seen": stamp,
            "last_seen": stamp,
        }
        existing.append(entry)
        index[k] = entry

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return existing
```

**Step 4: Run the new tests**

```
python -m pytest tests/test_listings_history.py -v
```

Expected: all 9 pass.

**Step 5: Run the full suite to catch regressions**

```
python -m pytest -v
```

Expected: all tests pass (46 from after PR #2 + 2 new from Task 1 + 9 new here = 57).

**Step 6: Commit**

```bash
git add tests/test_listings_history.py scraper/listings_history.py
git commit -m "feat: add listings history with dedup by (item_id, usd_cents)"
```

---

## Task 3: Wire merge_listings into the orchestrator

**Files:** Modify `scraper/scrape.py`.

**Step 1: Read the current file.**

**Step 2: Add import + constant**

Find the existing imports near the top:

```python
from .history import merge_sales
```

Replace with:

```python
from .history import merge_sales
from .listings_history import merge_listings
```

Find the existing path constants (look for `HISTORY_FILE = DATA_DIR / "sales_history.json"`):

```python
HISTORY_FILE = DATA_DIR / "sales_history.json"
```

Append below it:

```python
LISTINGS_HISTORY_FILE = DATA_DIR / "listings_history.json"
```

**Step 3: Call merge_listings after the existing merge_sales call**

Find the existing block:

```python
    try:
        history = merge_sales(snap["recent_sales"], HISTORY_FILE)
        history_count = len(history)
    except Exception as hist_err:  # noqa: BLE001 — history is opportunistic
        print(f"WARN: sales history merge failed: {hist_err}", file=sys.stderr)
        history_count = -1
```

Add a sibling block immediately after it:

```python
    try:
        listings_history = merge_listings(active_rows, LISTINGS_HISTORY_FILE)
        listings_history_count = len(listings_history)
    except Exception as hist_err:  # noqa: BLE001 — history is opportunistic
        print(f"WARN: listings history merge failed: {hist_err}", file=sys.stderr)
        listings_history_count = -1
```

(Pass `active_rows` — the **pre-cap source-level** list — not `snap["active_listings"]`.)

**Step 4: Extend the OK log line**

Find the final print:

```python
    print(
        f"OK: wrote {SNAPSHOT_FILE} with {len(prices)} prices, "
        f"{len(listings)} listings, {len(snap['recent_sales'])} recent sales, "
        f"{len(snap['active_listings'])} active listings, "
        f"history={history_count} ({counts_str})"
    )
```

Replace `history={history_count}` with `sales_history={history_count}, listings_history={listings_history_count}`. (Just a logging tweak; rename the local for clarity.)

**Step 5: Run the full test suite again**

```
python -m pytest -v
```

Expected: pass.

**Step 6: Local end-to-end smoke**

```
python -m scraper.scrape
```

Expected:
- Exit 0
- `data/listings_history.json` is created (or updated) with one entry per current active listing
- Console line: `OK: wrote ... sales_history=N1, listings_history=N2 (...)`

Read `data/listings_history.json` and confirm shape: each entry has `item_id`, `first_seen`, `last_seen` (equal on first run), and the other documented fields.

**Step 7: Commit**

```bash
git add scraper/scrape.py
git commit -m "feat: persist active listings to listings_history.json each cron"
```

---

## Task 4: Update tests/fixtures/README.md with a brief note

**Files:** Modify `tests/fixtures/README.md`.

Tiny addition — note that the `tests/test_listings_history.py` tests are fixture-free (don't reference these JSON fixtures). One sentence at the bottom, e.g.:

```
The listings-history tests in `tests/test_listings_history.py` are fixture-free —
they build payloads inline and write to `tmp_path`.
```

(Optional. Skip if it feels noisy.)

---

## Task 5: Push and open PR

**Step 1:**

```
git push -u origin feat/listings-history
```

**Step 2:**

```bash
gh pr create --title "feat: persist API-sourced listings to a deduped history" --body "$(cat <<'EOF'
## Summary
- New `data/listings_history.json`, deduped by `(item_id, usd_cents)`, written each cron. Survives eBay's effective listing-lifetime window.
- `_ebay_api_client._normalise_response` now emits `item_id` (sourced from the API's `itemId`); `merge_listings` is the only new user.
- 11 new unit tests (`tests/test_listings_history.py` + 2 in `test_source_ebay_api.py`).

## Test plan
- [x] Full test suite passes
- [x] Local end-to-end scrape produces a valid `data/listings_history.json` with first_seen == last_seen on first run
- [x] Re-run scrape updates last_seen on existing entries, no duplicates
- [ ] CI verification on the PR branch

## Reference
- Design: [docs/plans/2026-05-17-listings-history-design.md](docs/plans/2026-05-17-listings-history-design.md)
- Plan: [docs/plans/2026-05-17-listings-history.md](docs/plans/2026-05-17-listings-history.md)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Capture PR URL.

---

## Notes for the executing agent

- Strict TDD on Tasks 1 + 2. Failing test → run → confirm fail → implement → run → confirm pass → commit.
- One commit per task (4 commits total: feat-item-id, feat-history-module, feat-orchestrator-wire, optional README).
- Verification skills: `superpowers:test-driven-development` for Tasks 1 + 2, `superpowers:verification-before-completion` before each commit.
- `data/listings_history.json` will be created during the local smoke; **do not stage it** in the commit — that's the cron's job once the PR is merged.

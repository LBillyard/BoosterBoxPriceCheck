# Listings History — Design

**Date:** 2026-05-17
**Owner:** LBillyard

## Goal

Persist every API-sourced active listing we observe across cron runs, so we keep a long-term record beyond the eBay Browse API's effective listing-lifetime window. This pairs `data/listings_history.json` with the existing `data/sales_history.json`; together they form the local "we saw this" archive that survives anything that drops off eBay's search results.

## Why this matters

The Browse API only surfaces *currently* active listings. A booster box that sits at £35k for 40 days, drops to £32k for 10 days, then ends without selling is invisible to any post-hoc query — but those 50 days of price-watching data are exactly the trend signal we want for a long-running price-tracking display.

## Schema

`data/listings_history.json` is a flat JSON array; each entry is one observed `(item_id, usd_cents)` combination:

```json
[
  {
    "item_id": "v1|115678901234|0",
    "source": "ebay_api_us",
    "title": "1999 Pokemon Base Set Unlimited Booster Box WOTC Sealed",
    "usd_cents": 5000000,
    "gbp_cents": null,
    "url": "https://www.ebay.com/itm/115678901234",
    "seller_name": "garys_pokemart",
    "seller_feedback": 410,
    "seller_positive_pct": 100.0,
    "first_seen": "2026-05-17T14:00:00Z",
    "last_seen": "2026-05-19T02:00:00Z"
  }
]
```

- `item_id` — eBay's RESTful itemId (e.g. `"v1|115678901234|0"`). Captured fresh per PR — `_ebay_api_client._normalise_response` will be extended to surface it. Rows without `item_id` are skipped.
- `usd_cents` — integer USD-cents. Stable across runs even when FX rates wobble.
- `gbp_cents` — present only for UK (EBAY_GB) entries; `null` otherwise. Preserves the native-currency display.
- `first_seen` / `last_seen` — UTC ISO8601 with trailing `Z`. `first_seen` is set on insert and never changes. `last_seen` updates every cron run that still sees the entry.
- All other fields are carried forward from the source row at first observation. They are *not* refreshed on subsequent observations — if a seller's feedback score climbs from 410 to 415, the history entry keeps 410. This keeps the entry deterministic per dedup key.

## Dedup rule

The dedup key is the pair `(item_id, usd_cents)`. A listing that sits at one price forever is one entry. A listing whose price drops creates a second entry. A listing that ends and is then re-listed at the same price as before gets `last_seen` updated (we cannot detect "same itemId after re-listing" cleanly anyway).

Why not include `source`? Two marketplaces with the same `item_id` are the same physical listing (eBay's `itemId` is globally unique). If a seller cross-lists, we want one row — the source field becomes "the first one we saw."

## Merge logic

```python
def merge_listings(active_rows, history_path, now=None) -> list[dict]:
    """Merge currently-active rows into the on-disk history.

    Existing matches get their `last_seen` updated. Rows missing `item_id`
    are dropped. Entries already in the file that aren't in the current
    scrape are left untouched (we don't track "ended" — `last_seen` is the
    de facto end timestamp).
    """
```

The function mirrors the shape of `scraper.history.merge_sales` — load → dedup → write — but updates `last_seen` instead of skipping silent duplicates.

## Where it plugs in

`scraper/scrape.py` already calls `merge_sales(snap["recent_sales"], HISTORY_FILE)` after building the snapshot. We'll add a sibling call:

```python
merge_listings(active_rows, LISTINGS_HISTORY_FILE)
```

`active_rows` is the **pre-cap, source-level** list (not `snap["active_listings"]` which is capped at 25 and field-renamed). This guarantees the history captures everything the API returned, not just what fits in the snapshot view.

## File-cap policy

None initially. The history grows linearly with new listings + price changes; a generous back-of-envelope says ~5 new entries/day × 365 days = 1825 entries/year, with each row ~400 bytes → ~730 KB/year. We can revisit if the file crosses 10 MB. (For comparison `data/sales_history.json` is capped at `HISTORY_CAP=500` because sold rows are a tighter stream — listings are different.)

## Field-shape change to the API client

`_ebay_api_client._normalise_response` currently emits these keys:

```
title, usd_cents, [gbp_cents], date, url, seller_name, seller_feedback, seller_positive_pct
```

This PR adds `item_id` (sourced from the API's `itemId` field) as a new key on every row. Downstream consumers don't care today; `merge_listings` is the only new user. The existing `_normalise_active` in `scraper.snapshot` passes the field through (or strips it, depending on whether we want it in the snapshot) — design decision: **strip it from the snapshot's active_listings rows** to keep the snapshot a pure UI feed; the field is for history only.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Rows from before this PR don't have `item_id` because `_normalise_response` didn't capture it | A `git log`-fresh history file has no such rows. If someone is running the scraper locally with an old history file, it stays as-is until the first cron after merge — then new rows have `item_id`, old rows persist without it (no rule says they need it; only new merges check). |
| `item_id` shape changes (eBay rotation, format drift) | Treated as an opaque string. If it changes for an existing listing, we get a duplicate entry — acceptable. |
| File grows large | Yearly bytes estimate is sub-MB. Cap can be added later if needed. |
| Corrupt history file | `_load_existing` returns `[]` on JSONDecodeError — next cron rebuilds from scratch with current data. |
| Snapshot tests break because `_normalise_active` now strips a field | Existing tests don't assert on the presence/absence of `item_id` in snapshot rows, so should be fine. New tests for `_normalise_response` will check `item_id` is in the row. |

## Out of scope

- Web UI visualisation of the history (sparkline, "listed N days" badges, etc). The data lands first; UI can come later.
- HISTORY_CAP / age-based pruning. YAGNI.
- Tracking explicit "ended" events. `last_seen` is sufficient — anything not seen recently is by-definition not currently listed.
- Backfilling existing snapshots. The history starts when this PR lands.

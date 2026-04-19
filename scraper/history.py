"""Cumulative sales-history persistence.

Background
----------
``data/snapshot.json`` is overwritten on every scrape, and the eBay sources
only return the last ~90-day window of sold rows. Without persistence we
slowly forget every sale that drops off the SRP.

This module owns ``data/sales_history.json`` — a flat, append-mostly list
that survives across scrapes. Each new ``recent_sales`` row is merged in
once (deduped by URL when present, otherwise by a content hash), tagged
with a ``first_seen_at`` timestamp, sorted desc by ``date``, and capped at
``HISTORY_CAP`` entries.

The file is safe to delete: the next scrape rebuilds whatever is currently
in ``recent_sales`` and accumulates from there.

Schema
------
Each entry::

    {
      "source": "ebay_us",
      "title": "...",
      "usd": 42500.0,
      "gbp": 31403.0,
      "date": "2026-03-29",     # ISO date, possibly None
      "url": "https://...",      # possibly None
      "first_seen_at": "2026-04-19T16:58:22Z"
    }

The ``source/title/usd/gbp/date/url`` fields are exactly the
``recent_sales`` shape — this file is ``recent_sales`` extended in time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

# Hard cap on history length. Beyond ~500 the JSON file balloons past 200KB
# and the GitHub Pages payload starts to feel chunky. Older entries drop
# off the tail (sorted desc by date, so this is "drop oldest").
HISTORY_CAP = 500


def _dedupe_key(sale: dict) -> str:
    """Stable identity for a sale row.

    Prefer ``url`` — it's already unique on eBay/PriceCharting. Fall back
    to a hash of the rest so rows without URLs (130point, future sources)
    still dedupe correctly.
    """
    url = sale.get("url")
    if url:
        return f"url:{url}"
    blob = "|".join([
        str(sale.get("source") or ""),
        str(sale.get("title") or ""),
        str(sale.get("date") or ""),
        # int cents avoids float-formatting drift (42500.0 vs 42500.00).
        str(int(round(float(sale.get("usd") or 0) * 100))),
    ])
    return "h:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        # Corrupt history shouldn't kill the scrape — start fresh and let
        # the next run rebuild.
        return []


def _sort_desc(entries: list[dict]) -> list[dict]:
    """Sort desc by ``date``, with ``first_seen_at`` as tiebreaker.

    Empty/None dates fall to the end (matching how the UI orders them).
    """
    def key(e):
        return (e.get("date") or "", e.get("first_seen_at") or "")
    return sorted(entries, key=key, reverse=True)


def merge_sales(
    recent_sales: list[dict],
    history_path: Path,
    *,
    now: dt.datetime | None = None,
    cap: int = HISTORY_CAP,
) -> list[dict]:
    """Merge ``recent_sales`` into the history file at ``history_path``.

    New rows are prepended (logically — final order is by date) with a
    ``first_seen_at`` UTC ISO timestamp. Existing keys are skipped (no
    re-tagging, no field updates).

    Returns the full history list that was written, so callers can log
    counts or do further inspection.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    # Strip subseconds + force ``Z`` suffix for terse JSON.
    stamp = now.replace(microsecond=0).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    existing = _load_existing(history_path)
    seen = {_dedupe_key(e) for e in existing}

    merged = list(existing)
    for sale in recent_sales:
        key = _dedupe_key(sale)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "source": sale.get("source"),
            "title": sale.get("title"),
            "usd": sale.get("usd"),
            "gbp": sale.get("gbp"),
            "date": sale.get("date"),
            "url": sale.get("url"),
            "first_seen_at": stamp,
        }
        merged.append(entry)

    merged = _sort_desc(merged)[:cap]

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged

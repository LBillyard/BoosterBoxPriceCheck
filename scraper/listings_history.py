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

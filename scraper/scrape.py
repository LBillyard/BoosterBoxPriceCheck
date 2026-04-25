"""Entry point: fetch PriceCharting page, parse, fetch FX, write data files."""
import json
import os
import sys
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeoutError
from pathlib import Path

import requests

from .parser import parse_prices, parse_last_sold, parse_listings
from .fx import fetch_usd_to_gbp
from .snapshot import build_snapshot
from .history import merge_sales
from .sources import ebay_uk, ebay_us, ebay_us_active, ebay_pinned
# ebay_uk_active is intentionally not imported. Tried 3 URL variants
# (no filter / vintage query / sort-only) and every single one hung
# patchright on the GitHub Actions IP range. eBay UK refuses to serve
# active-listing SRPs to datacenter IPs regardless of URL shape.
# Wasted 3 min/cron for zero rows. Re-add when a working bypass lands.
#
# As a workaround, ebay_pinned fetches user-supplied item-page URLs
# directly (item pages DO render reliably for both .co.uk and .com).
# Add tracked listings in scraper/sources/ebay_pinned.py.

# Per-source hard ceiling. Patchright's internal timeouts are not
# always honoured when a page is stuck on a Cloudflare challenge, so we
# wrap every source fetch in a ThreadPoolExecutor and kill-wait at
# this boundary. 90s gives enough headroom for a normal patchright
# render (~25s) plus several item-page sub-fetches, while killing
# stuck sources fast enough to leave budget for retries within the
# workflow's 12-minute ceiling.
SOURCE_TIMEOUT_S = 90


def _run_with_timeout(name: str, fn, timeout_s: int = SOURCE_TIMEOUT_S) -> list:
    """Run fn() on a worker thread, abandon it if it overruns.

    CRITICAL: We deliberately do NOT use ``with ThreadPoolExecutor()``.
    The context manager's ``__exit__`` calls ``shutdown(wait=True)``,
    which blocks on the worker thread — and if the worker is stuck in
    a hung patchright navigation, shutdown waits forever. Each stuck
    source would then pin the runner until the workflow's own timeout
    killed it (observed: 3 stuck sources = full 12-min ceiling).

    Instead: explicit shutdown(wait=False) on timeout so we return
    immediately. The abandoned worker leaks until the Python process
    exits, which is fine — the workflow will exit cleanly after we
    write the snapshot, and patchright's browser is cleaned up then.
    """
    start = time.monotonic()
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn)
    try:
        rows = fut.result(timeout=timeout_s)
    except FutTimeoutError:
        elapsed = int(time.monotonic() - start)
        print(f"WARN: source {name} timed out after {elapsed}s", file=sys.stderr, flush=True)
        ex.shutdown(wait=False, cancel_futures=True)
        return []
    except Exception as e:  # noqa: BLE001
        elapsed = int(time.monotonic() - start)
        print(f"WARN: source {name} failed after {elapsed}s: {e}", file=sys.stderr, flush=True)
        ex.shutdown(wait=False, cancel_futures=True)
        return []
    ex.shutdown(wait=False)  # worker already finished; this is instant
    elapsed = int(time.monotonic() - start)
    print(f"INFO: source {name} returned {len(rows)} rows in {elapsed}s", file=sys.stderr, flush=True)
    return rows

URL = "https://www.pricecharting.com/game/pokemon-base-set/booster-box"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_FILE = DATA_DIR / "snapshot.json"
HISTORY_FILE = DATA_DIR / "sales_history.json"
ERROR_FILE = DATA_DIR / "error.json"

def fetch_page() -> str:
    r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text

def write_error(msg: str) -> None:
    ERROR_FILE.write_text(json.dumps({
        "error": msg,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }, indent=2))

def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    try:
        html = fetch_page()
    except Exception as e:
        write_error(f"fetch failed: {e}")
        print(f"ERROR: fetch failed: {e}", file=sys.stderr)
        return 1

    try:
        prices = parse_prices(html)
        last_sold = parse_last_sold(html)
        listings = parse_listings(html)
    except Exception as e:
        write_error(f"parse failed: {e}")
        print(f"ERROR: parse failed: {e}", file=sys.stderr)
        return 1

    if not prices:
        write_error("parser returned no prices — page structure may have changed")
        print("ERROR: no prices parsed", file=sys.stderr)
        return 1

    try:
        fx = fetch_usd_to_gbp()
    except Exception as e:
        fx = None
        if SNAPSHOT_FILE.exists():
            try:
                prev = json.loads(SNAPSHOT_FILE.read_text())
                fx = float(prev["fx"]["usd_to_gbp"])
                print(f"WARN: FX fetch failed, reusing previous rate {fx}", file=sys.stderr)
            except (ValueError, KeyError, json.JSONDecodeError) as fallback_err:
                write_error(f"FX fetch failed ({e}) and previous snapshot unreadable ({fallback_err})")
                return 1
        if fx is None:
            write_error(f"FX fetch failed and no previous rate: {e}")
            return 1

    # Recent sales from auxiliary sources. Each source is isolated AND
    # wrapped in a hard timeout so a stuck patchright session on one
    # source can't pin the whole scrape.
    #
    # 130point is currently excluded: Cloudflare blocks every patchright
    # variant we've tried, so the source always returns 0 and its
    # challenge-never-resolves failure mode was hanging the runner.
    # Re-add it if/when a stealth bypass lands.
    recent_sales: list[dict] = []
    source_counts: dict[str, int] = {}

    for name, fn in (
        ("ebay_uk",  lambda: ebay_uk.fetch(gbp_per_usd=fx)),
        ("ebay_us",  lambda: ebay_us.fetch()),
    ):
        rows = _run_with_timeout(name, fn)
        source_counts[name] = len(rows)
        recent_sales.extend(rows)

    # Also include the PriceCharting "last sold" so it appears in the
    # Recent Sales feed — otherwise the Last Sold card at the top of the
    # UI shows a value (e.g. a Heritage Auctions sale) that has no
    # matching row in the list, looking like a bug.
    if last_sold and last_sold.get("usd_cents"):
        usd = last_sold["usd_cents"] / 100.0
        recent_sales.append({
            "source": "pricecharting",
            "title": "Heritage / auction (via PriceCharting)",
            "usd_cents": last_sold["usd_cents"],
            "date": last_sold.get("date"),
            "url": "https://www.pricecharting.com/game/pokemon-base-set/booster-box",
            # PriceCharting reports the sale, not the seller — leave
            # seller fields None so the trust pill is suppressed for
            # auction-house rows (UI knows to skip non-eBay sources).
            "seller_name": None,
            "seller_feedback": None,
            "seller_positive_pct": None,
        })
        source_counts["pricecharting_last_sold"] = 1

    # Currently-active (Buy It Now) listings. ebay_us_active gets one
    # retry on empty/timeout — eBay's bot detection is intermittent
    # and a second patchright session often lands what the first
    # missed. (See import-line comment for why ebay_uk_active is
    # disabled.)
    active_rows: list[dict] = []
    rows = _run_with_timeout("ebay_us_active", lambda: ebay_us_active.fetch())
    if not rows:
        print("INFO: ebay_us_active returned 0; retrying once", file=sys.stderr, flush=True)
        rows = _run_with_timeout("ebay_us_active(retry)", lambda: ebay_us_active.fetch())
    source_counts["ebay_us_active"] = len(rows)
    active_rows.extend(rows)

    # User-pinned listings (workaround for the blocked ebay_uk SRP).
    # Each is fetched as an item page directly. Dedupe is handled by
    # build_snapshot's URL-based merge later.
    pinned = _run_with_timeout("ebay_pinned", lambda: ebay_pinned.fetch(gbp_per_usd=fx))
    source_counts["ebay_pinned"] = len(pinned)
    active_rows.extend(pinned)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    snap = build_snapshot(prices, last_sold, listings, fx, scraped_at=now,
                          recent_sales=recent_sales,
                          active_listings=active_rows)
    snap["source_counts"] = source_counts
    SNAPSHOT_FILE.write_text(json.dumps(snap, indent=2))

    # Persist this scrape's recent_sales into the long-running history file.
    # We feed the *normalised* rows (the snapshot shape) so the history
    # has the same fields as the UI expects.
    try:
        history = merge_sales(snap["recent_sales"], HISTORY_FILE)
        history_count = len(history)
    except Exception as hist_err:  # noqa: BLE001 — history is opportunistic
        print(f"WARN: sales history merge failed: {hist_err}", file=sys.stderr)
        history_count = -1

    if ERROR_FILE.exists():
        ERROR_FILE.unlink()
    counts_str = ", ".join(f"{k}={v}" for k, v in source_counts.items())
    print(
        f"OK: wrote {SNAPSHOT_FILE} with {len(prices)} prices, "
        f"{len(listings)} listings, {len(snap['recent_sales'])} recent sales, "
        f"{len(snap['active_listings'])} active listings, "
        f"history={history_count} ({counts_str})"
    )
    return 0

if __name__ == "__main__":
    rc = main()
    # If a source timed out, its abandoned worker thread is still alive
    # running a hung patchright browser. Python's atexit machinery joins
    # all non-daemon threads on interpreter shutdown, so a normal
    # sys.exit() would block forever waiting for that leaked thread.
    # We've already written the snapshot, so bypass atexit entirely.
    os._exit(rc)

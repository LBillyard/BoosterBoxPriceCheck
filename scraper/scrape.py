"""Entry point: fetch PriceCharting page, parse, fetch FX, write data files."""
import json
import sys
import datetime as dt
from pathlib import Path

import requests

from .parser import parse_prices, parse_last_sold, parse_listings
from .fx import fetch_usd_to_gbp
from .snapshot import build_snapshot

URL = "https://www.pricecharting.com/game/pokemon-base-set/booster-box"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_FILE = DATA_DIR / "snapshot.json"
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

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    snap = build_snapshot(prices, last_sold, listings, fx, scraped_at=now)
    SNAPSHOT_FILE.write_text(json.dumps(snap, indent=2))
    if ERROR_FILE.exists():
        ERROR_FILE.unlink()
    print(f"OK: wrote {SNAPSHOT_FILE} with {len(prices)} prices, {len(listings)} listings")
    return 0

if __name__ == "__main__":
    sys.exit(main())

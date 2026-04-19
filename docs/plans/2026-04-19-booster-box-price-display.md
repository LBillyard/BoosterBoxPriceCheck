# Booster Box Price Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a static-site price display for a Pokémon Base Set Booster Box, fed by a 12-hourly GitHub Actions scrape of PriceCharting and FX rates, hosted on GitHub Pages, installable as a PWA on a cheap Android phone.

**Architecture:** Python scraper runs in GitHub Actions every 12 hours, parses the PriceCharting product page + USD→GBP rate from frankfurter.app, and commits `data/snapshot.json` back to the repo. A static HTML/JS/CSS frontend served from GitHub Pages fetches that JSON and renders a clean white display.

**Tech Stack:** Python 3.11, `requests`, `beautifulsoup4`, `pytest`. Vanilla HTML/CSS/JS. GitHub Actions, GitHub Pages.

**Design doc:** [docs/plans/2026-04-19-booster-box-price-display-design.md](2026-04-19-booster-box-price-display-design.md)

---

## Task 1: Project skeleton

**Files:**
- Create: `scraper/requirements.txt`
- Create: `scraper/__init__.py`
- Create: `scraper/scrape.py` (empty stub)
- Create: `scraper/parser.py` (empty stub)
- Create: `scraper/fx.py` (empty stub)
- Create: `tests/__init__.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `web/.gitkeep`
- Create: `data/.gitkeep`

**Step 1: Create the directories and stub files**

```bash
cd /c/Users/Shadow/Desktop/BoosterBoxPriceCheck
mkdir -p scraper tests/fixtures web data
touch scraper/__init__.py tests/__init__.py tests/fixtures/.gitkeep web/.gitkeep data/.gitkeep
```

**Step 2: Write `scraper/requirements.txt`**

```
requests==2.32.3
beautifulsoup4==4.12.3
pytest==8.3.3
```

**Step 3: Commit**

```bash
git add scraper tests web data
git commit -m "chore: project skeleton"
```

---

## Task 2: Save a real PriceCharting page as a test fixture

We need real HTML to write parser tests against. Cannot scrape from inside Claude (blocked) — the user (or executing agent on a real network) will fetch it once.

**Files:**
- Create: `tests/fixtures/booster_box.html`

**Step 1: Fetch the page with a real browser User-Agent**

```bash
curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" \
  "https://www.pricecharting.com/game/pokemon-base-set/booster-box" \
  -o tests/fixtures/booster_box.html
```

Expected: file >50KB containing `<html` and `Booster Box`.

**Step 2: Sanity-check the file**

```bash
ls -la tests/fixtures/booster_box.html
grep -c "Booster Box" tests/fixtures/booster_box.html
```

Expected: file size > 50000 bytes; "Booster Box" appears multiple times.

**Step 3: Commit**

```bash
git add tests/fixtures/booster_box.html
git commit -m "test: add PriceCharting page fixture"
```

---

## Task 3: Parser — extract current prices

**Files:**
- Create: `tests/test_parser_prices.py`
- Modify: `scraper/parser.py`

**Step 1: Write the failing test**

`tests/test_parser_prices.py`:
```python
from pathlib import Path
from scraper.parser import parse_prices

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_prices_returns_known_conditions():
    html = FIXTURE.read_text(encoding="utf-8")
    prices = parse_prices(html)
    # PriceCharting always shows at least these for sealed product:
    assert "loose" in prices or "new" in prices or "sealed" in prices
    # Every value should be an int number of cents (matches API convention)
    for cond, cents in prices.items():
        assert isinstance(cents, int), f"{cond} should be int cents"
        assert cents > 100_000, f"{cond}={cents} suspiciously low for a Base Set box"
```

**Step 2: Run test to verify it fails**

```bash
cd /c/Users/Shadow/Desktop/BoosterBoxPriceCheck
python -m pytest tests/test_parser_prices.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` on `parse_prices`.

**Step 3: Implement the parser**

`scraper/parser.py`:
```python
from bs4 import BeautifulSoup
import re

PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{2})?)")

def _to_cents(price_text: str) -> int | None:
    m = PRICE_RE.search(price_text)
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", "")) * 100))

def parse_prices(html: str) -> dict[str, int]:
    """Extract current prices per condition from a PriceCharting product page.

    Returns dict like {"loose": 3642000, "cib": 2280000, ...} where values
    are integer cents (USD).
    """
    soup = BeautifulSoup(html, "html.parser")
    prices: dict[str, int] = {}

    # PriceCharting wraps each price in a table with id like "used_price",
    # "complete_price", "new_price", and for sealed product also "graded_price".
    for table_id, label in [
        ("used_price", "loose"),
        ("complete_price", "cib"),
        ("new_price", "new"),
        ("graded_price", "sealed"),
        ("box_only_price", "box_only"),
        ("manual_only_price", "manual_only"),
    ]:
        el = soup.find(id=table_id)
        if not el:
            continue
        text = el.get_text(" ", strip=True)
        cents = _to_cents(text)
        if cents:
            prices[label] = cents
    return prices
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_parser_prices.py -v
```

Expected: PASS. If it fails because the IDs differ on PriceCharting, open `tests/fixtures/booster_box.html`, find the price elements, and update the IDs in `parse_prices`.

**Step 5: Commit**

```bash
git add scraper/parser.py tests/test_parser_prices.py
git commit -m "feat(scraper): parse current prices per condition"
```

---

## Task 4: Parser — extract last sold

**Files:**
- Create: `tests/test_parser_last_sold.py`
- Modify: `scraper/parser.py`

**Step 1: Write the failing test**

`tests/test_parser_last_sold.py`:
```python
from pathlib import Path
from scraper.parser import parse_last_sold

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_last_sold_returns_price_and_date():
    html = FIXTURE.read_text(encoding="utf-8")
    result = parse_last_sold(html)
    assert result is not None
    assert isinstance(result["usd_cents"], int)
    assert result["usd_cents"] > 100_000
    assert result["date"]  # ISO date string
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_parser_last_sold.py -v
```

Expected: FAIL — `parse_last_sold` not defined.

**Step 3: Implement**

Append to `scraper/parser.py`:
```python
def parse_last_sold(html: str) -> dict | None:
    """Find the most recent recorded sale on the page.

    Returns {"usd_cents": int, "date": "YYYY-MM-DD"} or None.
    """
    soup = BeautifulSoup(html, "html.parser")

    # PriceCharting's recent sales table has class "sales" or id "sales_table".
    # Each row has a date cell and a price cell.
    table = soup.find(id="sales_table") or soup.find("table", class_="sales")
    if not table:
        return None

    first_row = table.find("tr", attrs={"data-product-id": True}) or (
        table.find_all("tr")[1] if len(table.find_all("tr")) > 1 else None
    )
    if not first_row:
        return None

    cells = first_row.find_all("td")
    if len(cells) < 2:
        return None

    date_text = cells[0].get_text(strip=True)
    price_text = cells[-1].get_text(strip=True)

    cents = _to_cents(price_text)
    if not cents:
        return None

    # Date format on PC is typically "YYYY-MM-DD" or "MMM DD, YYYY"
    return {"usd_cents": cents, "date": date_text}
```

**Step 4: Run test**

```bash
python -m pytest tests/test_parser_last_sold.py -v
```

Expected: PASS. If it fails, inspect the HTML around the recent sales section in the fixture, and adjust the selector.

**Step 5: Commit**

```bash
git add scraper/parser.py tests/test_parser_last_sold.py
git commit -m "feat(scraper): parse last sold price and date"
```

---

## Task 5: Parser — extract active marketplace listings

**Files:**
- Create: `tests/test_parser_listings.py`
- Modify: `scraper/parser.py`

**Step 1: Write the failing test**

`tests/test_parser_listings.py`:
```python
from pathlib import Path
from scraper.parser import parse_listings

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_listings_returns_list_of_dicts():
    html = FIXTURE.read_text(encoding="utf-8")
    listings = parse_listings(html)
    # Booster boxes are not always listed; allow empty but type must be list.
    assert isinstance(listings, list)
    for item in listings:
        assert "usd_cents" in item
        assert isinstance(item["usd_cents"], int)
        assert "condition" in item
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_parser_listings.py -v
```

Expected: FAIL — `parse_listings` not defined.

**Step 3: Implement**

Append to `scraper/parser.py`:
```python
def parse_listings(html: str) -> list[dict]:
    """Extract active marketplace listings (eBay etc.) shown on the page.

    Returns a list of {"usd_cents": int, "condition": str, "seller": str|None,
    "url": str|None}. May be empty.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []

    # PriceCharting embeds an "Items For Sale" table with id "listings_table"
    # or a section containing rows of seller/price/condition.
    table = soup.find(id="listings_table") or soup.find(id="items_for_sale")
    if not table:
        return out

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        # Look for a price in any cell
        price_cents = None
        for c in cells:
            cents = _to_cents(c.get_text(" ", strip=True))
            if cents:
                price_cents = cents
                break
        if not price_cents:
            continue
        condition = cells[0].get_text(" ", strip=True) or "Unknown"
        link = row.find("a", href=True)
        out.append({
            "usd_cents": price_cents,
            "condition": condition,
            "seller": None,
            "url": link["href"] if link else None,
        })
    return out
```

**Step 4: Run test**

```bash
python -m pytest tests/test_parser_listings.py -v
```

Expected: PASS. If the listings table on PC uses a different ID, inspect the fixture and adjust.

**Step 5: Commit**

```bash
git add scraper/parser.py tests/test_parser_listings.py
git commit -m "feat(scraper): parse active marketplace listings"
```

---

## Task 6: FX rate fetcher

**Files:**
- Create: `tests/test_fx.py`
- Modify: `scraper/fx.py`

**Step 1: Write the test**

`tests/test_fx.py`:
```python
from unittest.mock import patch
from scraper.fx import fetch_usd_to_gbp

def test_fetch_usd_to_gbp_parses_response():
    fake = {"amount": 1.0, "base": "USD", "date": "2026-04-19", "rates": {"GBP": 0.7945}}
    with patch("scraper.fx.requests.get") as m:
        m.return_value.json.return_value = fake
        m.return_value.raise_for_status.return_value = None
        rate = fetch_usd_to_gbp()
    assert rate == 0.7945
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_fx.py -v
```

Expected: FAIL — function not defined.

**Step 3: Implement**

`scraper/fx.py`:
```python
import requests

FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=GBP"

def fetch_usd_to_gbp(timeout: int = 10) -> float:
    r = requests.get(FRANKFURTER_URL, timeout=timeout)
    r.raise_for_status()
    return float(r.json()["rates"]["GBP"])
```

**Step 4: Run test**

```bash
python -m pytest tests/test_fx.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add scraper/fx.py tests/test_fx.py
git commit -m "feat(scraper): fetch USD->GBP rate from frankfurter.app"
```

---

## Task 7: Snapshot builder (combines parser output + FX into JSON)

**Files:**
- Create: `tests/test_snapshot.py`
- Create: `scraper/snapshot.py`

**Step 1: Write the test**

`tests/test_snapshot.py`:
```python
from scraper.snapshot import build_snapshot

def test_build_snapshot_converts_currencies_and_includes_purchase_price():
    prices = {"loose": 3642000, "new": 3680000}
    last_sold = {"usd_cents": 3575000, "date": "2026-04-17"}
    listings = [{"usd_cents": 3460000, "condition": "Sealed", "seller": None, "url": None}]
    fx = 0.80
    snap = build_snapshot(prices, last_sold, listings, fx, scraped_at="2026-04-19T12:00:00Z")

    assert snap["fx"]["usd_to_gbp"] == 0.80
    assert snap["prices"]["loose"]["usd"] == 36420
    assert snap["prices"]["loose"]["gbp"] == round(36420 * 0.80, 2)
    assert snap["last_sold"]["gbp"] == round(35750 * 0.80, 2)
    assert snap["listings"][0]["gbp"] == round(34600 * 0.80, 2)
    assert snap["purchase_price_gbp"] == 29253.05
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_snapshot.py -v
```

Expected: FAIL — module not found.

**Step 3: Implement**

`scraper/snapshot.py`:
```python
PURCHASE_PRICE_GBP = 29253.05

def _cents_to_dollars(cents: int) -> float:
    return round(cents / 100, 2)

def _convert(usd: float, fx: float) -> float:
    return round(usd * fx, 2)

def build_snapshot(prices, last_sold, listings, fx, scraped_at: str) -> dict:
    out_prices = {}
    for cond, cents in prices.items():
        usd = _cents_to_dollars(cents)
        out_prices[cond] = {"usd": usd, "gbp": _convert(usd, fx)}

    out_last_sold = None
    if last_sold:
        usd = _cents_to_dollars(last_sold["usd_cents"])
        out_last_sold = {"usd": usd, "gbp": _convert(usd, fx), "date": last_sold["date"]}

    out_listings = []
    for item in listings:
        usd = _cents_to_dollars(item["usd_cents"])
        out_listings.append({
            "condition": item["condition"],
            "usd": usd,
            "gbp": _convert(usd, fx),
            "seller": item.get("seller"),
            "url": item.get("url"),
        })

    return {
        "scraped_at": scraped_at,
        "fx": {"usd_to_gbp": fx, "fetched_at": scraped_at},
        "prices": out_prices,
        "last_sold": out_last_sold,
        "listings": out_listings,
        "purchase_price_gbp": PURCHASE_PRICE_GBP,
    }
```

**Step 4: Run test**

```bash
python -m pytest tests/test_snapshot.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add scraper/snapshot.py tests/test_snapshot.py
git commit -m "feat(scraper): build combined snapshot JSON with GBP conversions"
```

---

## Task 8: Scraper entry point (orchestrator)

**Files:**
- Modify: `scraper/scrape.py`

**Step 1: Implement the entry point**

`scraper/scrape.py`:
```python
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
        # Reuse last-known FX if available
        if SNAPSHOT_FILE.exists():
            prev = json.loads(SNAPSHOT_FILE.read_text())
            fx = prev["fx"]["usd_to_gbp"]
            print(f"WARN: FX fetch failed, reusing previous rate {fx}", file=sys.stderr)
        else:
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
```

**Step 2: Run it locally**

```bash
cd /c/Users/Shadow/Desktop/BoosterBoxPriceCheck
python -m pip install -r scraper/requirements.txt
python -m scraper.scrape
```

Expected: prints `OK: wrote ... with N prices, M listings`. `data/snapshot.json` exists.

**Step 3: Inspect the output**

```bash
cat data/snapshot.json | head -40
```

Expected: well-formed JSON matching the design doc shape.

**Step 4: Commit**

```bash
git add scraper/scrape.py data/snapshot.json
git commit -m "feat(scraper): orchestrator + first real snapshot"
```

---

## Task 9: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/scrape.yml`

**Step 1: Write the workflow**

```yaml
name: Scrape PriceCharting

on:
  schedule:
    - cron: "0 */12 * * *"  # every 12 hours
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r scraper/requirements.txt

      - name: Run scraper
        run: python -m scraper.scrape

      - name: Commit snapshot
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --cached --quiet; then
            echo "No changes to commit."
          else
            git commit -m "chore: snapshot $(date -u +'%Y-%m-%d %H:%M UTC')"
            git push
          fi
```

**Step 2: Commit and push**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci: add 12-hourly scrape workflow"
git push
```

**Step 3: Trigger a manual run to verify**

```bash
gh workflow run scrape.yml
sleep 30
gh run list --workflow=scrape.yml --limit 1
gh run view --log $(gh run list --workflow=scrape.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

Expected: workflow completes with success. If it fails on parse (GH IPs blocked) — see Task 14 (Playwright fallback).

---

## Task 10: Frontend HTML

**Files:**
- Create: `web/index.html`

**Step 1: Write the page**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>Base Set Booster Box</title>
  <link rel="stylesheet" href="style.css">
  <link rel="manifest" href="manifest.webmanifest">
</head>
<body>
  <main id="app">
    <header>
      <h1>Base Set Booster Box</h1>
      <p id="updated" class="muted">Loading…</p>
    </header>

    <section class="hero">
      <p class="hero-gbp" id="hero-gbp">—</p>
      <p class="hero-usd muted" id="hero-usd">—</p>
    </section>

    <section class="conditions" id="conditions"></section>

    <section class="last-sold">
      <h2>Last sold</h2>
      <p id="last-sold">—</p>
    </section>

    <section class="listings">
      <h2 id="listings-summary">Listings</h2>
      <ol id="listings-list"></ol>
    </section>

    <footer>
      <button id="refresh">Refresh</button>
      <p id="error" class="error" hidden></p>
    </footer>
  </main>
  <script src="app.js"></script>
</body>
</html>
```

**Step 2: Commit**

```bash
git add web/index.html
git commit -m "feat(web): page skeleton"
```

---

## Task 11: Frontend CSS (clean white)

**Files:**
- Create: `web/style.css`

**Step 1: Write the styles**

```css
:root {
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #6b6b6b;
  --accent: #2f7a4d;
  --border: #ececec;
  --warn: #c08a00;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg); color: var(--fg); }
body {
  font: 16px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}
#app {
  max-width: 480px;
  margin: 0 auto;
  padding: 24px 20px 64px;
}
header h1 { font-size: 18px; font-weight: 500; }
.muted { color: var(--muted); font-size: 13px; }
.hero { text-align: center; padding: 32px 0 16px; }
.hero-gbp { font-size: 56px; font-weight: 600; color: var(--accent); letter-spacing: -1px; }
.hero-usd { font-size: 18px; margin-top: 4px; }
.conditions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 24px 0; }
.condition {
  border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 8px; text-align: center;
}
.condition .label { font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.5px; }
.condition .value { font-size: 16px; font-weight: 500; margin-top: 4px; }
section h2 { font-size: 12px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.6px; margin: 24px 0 8px; }
.last-sold p { font-size: 18px; }
.listings ol { list-style: none; }
.listings li {
  display: grid; grid-template-columns: 1fr auto auto; gap: 12px; align-items: baseline;
  padding: 10px 0; border-bottom: 1px solid var(--border);
}
.listings li .cond { color: var(--muted); font-size: 13px; }
.listings li .gbp { font-weight: 500; }
.listings li .usd { color: var(--muted); font-size: 13px; min-width: 64px; text-align: right; }
footer { margin-top: 32px; text-align: center; }
button {
  background: var(--fg); color: white; border: 0;
  padding: 10px 24px; border-radius: 999px; font-size: 14px; cursor: pointer;
}
.error { color: var(--warn); margin-top: 12px; font-size: 13px; }
.stale { color: var(--warn); }
```

**Step 2: Commit**

```bash
git add web/style.css
git commit -m "feat(web): clean white styling"
```

---

## Task 12: Frontend JS (fetch + render)

**Files:**
- Create: `web/app.js`

**Step 1: Write the renderer**

```javascript
const DATA_URL = "../data/snapshot.json";  // relative when served from /web with data/ alongside; see Task 13
const POLL_MS = 5 * 60 * 1000;

const fmtGBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const fmtUSD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function relative(iso) {
  const t = new Date(iso).getTime();
  const diffMin = Math.round((Date.now() - t) / 60000);
  if (diffMin < 60) return `${diffMin}m ago`;
  const h = Math.round(diffMin / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

async function load() {
  const errEl = document.getElementById("error");
  errEl.hidden = true;
  try {
    const r = await fetch(DATA_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
  } catch (e) {
    errEl.textContent = `Could not load data: ${e.message}`;
    errEl.hidden = false;
  }
}

function render(snap) {
  const updatedEl = document.getElementById("updated");
  const ageHrs = (Date.now() - new Date(snap.scraped_at).getTime()) / 3_600_000;
  updatedEl.textContent = `Updated ${relative(snap.scraped_at)}`;
  if (ageHrs > 24) updatedEl.classList.add("stale");

  const hero = snap.prices.loose || snap.prices.new || snap.prices.sealed || Object.values(snap.prices)[0];
  document.getElementById("hero-gbp").textContent = fmtGBP.format(hero.gbp);
  document.getElementById("hero-usd").textContent = fmtUSD.format(hero.usd);

  const cEl = document.getElementById("conditions");
  cEl.innerHTML = "";
  for (const [label, vals] of Object.entries(snap.prices)) {
    const div = document.createElement("div");
    div.className = "condition";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${fmtGBP.format(vals.gbp)}</div>`;
    cEl.appendChild(div);
  }

  const lsEl = document.getElementById("last-sold");
  if (snap.last_sold) {
    lsEl.textContent = `${fmtGBP.format(snap.last_sold.gbp)} · ${snap.last_sold.date}`;
  } else {
    lsEl.textContent = "No recorded sales";
  }

  const sumEl = document.getElementById("listings-summary");
  const list = document.getElementById("listings-list");
  list.innerHTML = "";
  if (snap.listings && snap.listings.length) {
    const min = Math.min(...snap.listings.map(l => l.gbp));
    sumEl.textContent = `${snap.listings.length} listed · from ${fmtGBP.format(min)}`;
    for (const item of snap.listings) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="cond">${item.condition}</span>
        <span class="gbp">${fmtGBP.format(item.gbp)}</span>
        <span class="usd">${fmtUSD.format(item.usd)}</span>`;
      list.appendChild(li);
    }
  } else {
    sumEl.textContent = "No active listings";
  }
}

document.getElementById("refresh").addEventListener("click", load);
load();
setInterval(load, POLL_MS);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
```

**Step 2: Commit**

```bash
git add web/app.js
git commit -m "feat(web): fetch and render snapshot"
```

---

## Task 13: GitHub Pages deploy + data path

GitHub Pages will serve `web/` as the site root. The data file lives at `data/snapshot.json`. We need the frontend to be able to fetch it from the same origin.

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `web/app.js` (data URL)

**Step 1: Make a Pages-friendly layout via the workflow**

We will *publish* a built site that contains both `web/` content and a `data/` symlink/copy. The simplest path: copy `data/` into `web/data/` as part of the deploy job.

`.github/workflows/pages.yml`:
```yaml
name: Deploy GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - "web/**"
      - "data/**"
      - ".github/workflows/pages.yml"
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Assemble site
        run: |
          mkdir -p _site
          cp -r web/. _site/
          mkdir -p _site/data
          cp -r data/. _site/data/ || true

      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Update `web/app.js` data URL**

Change in `web/app.js`:
```javascript
const DATA_URL = "data/snapshot.json";
```

(Same-origin path, since the deploy step copies `data/` into the site root.)

**Step 3: Enable Pages**

```bash
gh repo edit LBillyard/BoosterBoxPriceCheck --enable-issues=false
# Enable Pages with GitHub Actions source:
gh api -X POST repos/LBillyard/BoosterBoxPriceCheck/pages \
  -f build_type=workflow || echo "Pages may already be enabled"
```

**Step 4: Commit + push**

```bash
git add .github/workflows/pages.yml web/app.js
git commit -m "ci: deploy GitHub Pages site with data/ copied alongside"
git push
```

**Step 5: Verify**

```bash
sleep 30
gh run list --workflow=pages.yml --limit 1
```

Open: `https://lbillyard.github.io/BoosterBoxPriceCheck/`

Expected: page loads with the latest snapshot.

---

## Task 14: PWA manifest + service worker

**Files:**
- Create: `web/manifest.webmanifest`
- Create: `web/sw.js`
- Create: `web/icon-192.png` and `web/icon-512.png` (placeholder solid-colour PNGs)

**Step 1: Manifest**

`web/manifest.webmanifest`:
```json
{
  "name": "Base Set Booster Box",
  "short_name": "Booster Box",
  "start_url": "./",
  "scope": "./",
  "display": "fullscreen",
  "orientation": "portrait",
  "background_color": "#ffffff",
  "theme_color": "#ffffff",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

**Step 2: Service worker (minimal — cache-first for shell, network for data)**

`web/sw.js`:
```javascript
const CACHE = "boosterbox-v1";
const SHELL = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("/data/snapshot.json")) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  } else {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
```

**Step 3: Generate placeholder icons**

```bash
cd /c/Users/Shadow/Desktop/BoosterBoxPriceCheck
python -c "
from PIL import Image
for size in (192, 512):
    img = Image.new('RGB', (size, size), (47, 122, 77))
    img.save(f'web/icon-{size}.png')
"
```

If PIL is not installed: `pip install Pillow` first. (Or replace later with proper icons.)

**Step 4: Commit and push**

```bash
git add web/manifest.webmanifest web/sw.js web/icon-192.png web/icon-512.png
git commit -m "feat(web): PWA manifest, service worker, placeholder icons"
git push
```

**Step 5: Verify on phone**

On the cheap Android phone: open `https://lbillyard.github.io/BoosterBoxPriceCheck/` in Chrome → menu → "Add to Home screen" / "Install app". Tap the icon: full-screen, no URL bar.

---

## Task 15: Wake-lock so the screen doesn't sleep

When opened as a PWA, the phone screen will dim/sleep. The Wake Lock API keeps it on while the page is visible.

**Files:**
- Modify: `web/app.js`

**Step 1: Append to `web/app.js`**

```javascript
// Keep screen awake while the app is visible (PWA only).
let wakeLock = null;
async function requestWakeLock() {
  if (!("wakeLock" in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch (e) {
    console.warn("wake lock denied:", e);
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") requestWakeLock();
});
requestWakeLock();
```

**Step 2: Commit + push**

```bash
git add web/app.js
git commit -m "feat(web): keep screen awake via Wake Lock API"
git push
```

---

## Task 16: Fallback — Playwright if HTTP scrape is blocked

If Task 9 (workflow) fails with 403 or returns an HTML page that doesn't contain prices (PriceCharting may serve a Cloudflare challenge to GitHub IPs), swap the fetcher.

**Files:**
- Modify: `scraper/scrape.py` (use Playwright)
- Modify: `scraper/requirements.txt`
- Modify: `.github/workflows/scrape.yml` (install browsers)

**Step 1: Add dependency**

`scraper/requirements.txt`:
```
requests==2.32.3
beautifulsoup4==4.12.3
pytest==8.3.3
playwright==1.47.0
```

**Step 2: Replace `fetch_page` in `scraper/scrape.py`**

```python
def fetch_page() -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#used_price, #new_price, #graded_price", timeout=15000)
        html = page.content()
        browser.close()
        return html
```

**Step 3: Update workflow to install browsers**

In `.github/workflows/scrape.yml`, after `pip install -r ...`:
```yaml
      - name: Install Playwright browsers
        run: python -m playwright install --with-deps chromium
```

**Step 4: Commit + push + retry**

```bash
git add scraper/requirements.txt scraper/scrape.py .github/workflows/scrape.yml
git commit -m "fix(scraper): use Playwright headless browser to bypass IP blocking"
git push
gh workflow run scrape.yml
```

---

## Task 17: README polish

**Files:**
- Modify: `README.md`

**Step 1: Update with live links and screenshot**

Replace `README.md` with:
```markdown
# BoosterBoxPriceCheck

Always-on price display for a Pokémon Base Set Booster Box.

🔗 **Live page:** https://lbillyard.github.io/BoosterBoxPriceCheck/

A GitHub Actions cron scrapes [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/booster-box) every 12 hours, fetches USD→GBP from [frankfurter.app](https://www.frankfurter.app/), and commits the snapshot. The static site fetches the snapshot and renders a clean white display. Installable as a PWA on Android (Add to Home screen) for a permanent always-on phone display.

## Layout

- `scraper/` — Python scraper (parser, FX, orchestrator)
- `tests/` — pytest tests with HTML fixture
- `web/` — static frontend (HTML, JS, CSS, PWA manifest, service worker)
- `data/` — committed snapshots from the cron
- `.github/workflows/` — scrape (cron) + pages (deploy)

## Running locally

```bash
pip install -r scraper/requirements.txt
python -m scraper.scrape   # writes data/snapshot.json
python -m http.server -d web 8000
# Open http://localhost:8000
```

## Tests

```bash
python -m pytest -v
```
```

**Step 2: Commit + push**

```bash
git add README.md
git commit -m "docs: polish README with live link and instructions"
git push
```

---

## Done

After all tasks: live page on GitHub Pages, cron updates every 12 hours, install as PWA on the phone.

## Reference skills
- @superpowers:test-driven-development for the parser tests
- @superpowers:verification-before-completion before marking the workflow run as "working"

# eBay API Source — Design

**Date:** 2026-05-16
**Owner:** LBillyard
**Tracked item:** [Pokémon Base Set Booster Box on PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/booster-box)

## Goal

Add an official-eBay-API-backed source alongside the existing patchright SRP scrapers. The API path is more reliable on GitHub Actions IPs (no bot-detection JS shell), gives structured JSON instead of HTML, and removes the ~25s-per-fetch Chromium spin-up cost.

The current `ebay_us` / `ebay_uk` scrapers stay in place. The new API source runs as a separate, isolated source — if one path breaks, the other still feeds the snapshot.

## Scope

**In scope (this design):**
- Active listings (Buy It Now) on `ebay.com` and `ebay.co.uk` via the **Browse API** (`/buy/browse/v1/item_summary/search`).
- OAuth Application Token (client_credentials grant) with in-process token cache.
- Two new sources: `scraper/sources/ebay_api_us.py`, `scraper/sources/ebay_api_uk.py`.
- Shared transport helper: `scraper/sources/_ebay_api_client.py`.
- Credentials via environment variables `EBAY_CLIENT_ID` + `EBAY_CLIENT_SECRET`, sourced from `.env` locally and GitHub Secrets in CI.

**In scope (process, not code):**
- Walk through eBay Developer Program signup in the user's Chrome browser.
- Submit the **Marketplace Insights API** application (sold-listings data). Approval is uncertain; deferred from this design until granted.

**Out of scope:**
- Marketplace Insights API integration (separate design once / if access is granted).
- Replacing the SRP scrapers.
- Sandbox keyset.
- User-context OAuth (we only need public listing data).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ scraper/scrape.py (orchestrator)                                │
│                                                                 │
│  for name, fn in (                                              │
│    ("ebay_uk",      ebay_uk.fetch),                  ── SRP     │
│    ("ebay_us",      ebay_us.fetch),                  ── SRP     │
│    ("ebay_api_us",  ebay_api_us.fetch),              ── API new │
│    ("ebay_api_uk",  ebay_api_uk.fetch),              ── API new │
│  ): rows = _run_with_timeout(name, fn)                          │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────┐    ┌────────────────────────────┐
│ ebay_api_us.py / _uk.py      │    │ _ebay_api_client.py        │
│ - set marketplace + currency │───▶│ - OAuth token (cached 2h)  │
│ - filter via is_acceptable   │    │ - browse_search(...)       │
│ - tag source field           │    │ - JSON → dict normalise    │
└──────────────────────────────┘    └────────────────────────────┘
                                                 │
                                                 ▼
                                    ┌────────────────────────────┐
                                    │ api.ebay.com               │
                                    │ /identity/v1/oauth2/token  │
                                    │ /buy/browse/v1/...         │
                                    └────────────────────────────┘
```

## Components

### 1. `scraper/sources/_ebay_api_client.py` (transport)

Mirrors `_browser.py` — does transport + normalisation, no parsing logic specific to the search query. Exports:

```python
def browse_search(
    query: str,
    marketplace: str,           # "EBAY_US" | "EBAY_GB"
    limit: int = 50,
    filter_expr: str | None = None,  # eBay's filter mini-language, e.g. "price:[15000..],priceCurrency:USD"
    timeout: int = 20,
) -> list[dict]:
    """Return normalised active-listing rows (snapshot shape) for the given query+marketplace."""
```

Internals:
- **Token cache**: module-global `(access_token, expires_at_epoch)` tuple. `_get_token()` checks expiry against `time.time() + 60` (60s safety margin), refreshes via POST to `https://api.ebay.com/identity/v1/oauth2/token` with `grant_type=client_credentials`, `scope=https://api.ebay.com/oauth/api_scope`, Basic auth = `base64(client_id:client_secret)`.
- **Credentials**: read once at module import from `os.environ["EBAY_CLIENT_ID"]` / `EBAY_CLIENT_SECRET`. Missing creds → raise `RuntimeError` (the orchestrator's try/except converts this to "0 rows" so the snapshot still writes).
- **Search call**: `GET https://api.ebay.com/buy/browse/v1/item_summary/search` with headers `Authorization: Bearer <token>` and `X-EBAY-C-MARKETPLACE-ID: <marketplace>`.
- **Normalisation**: convert each `itemSummary` to the existing snapshot row shape (see Data schema below).
- **Failure mode**: any exception (network, 401, 403, malformed JSON) → return `[]`. Logging via `print(..., file=sys.stderr)` matching the rest of the codebase.

### 2. `scraper/sources/ebay_api_us.py` and `ebay_api_uk.py`

Thin wrappers — set marketplace, currency expectation, search query, then delegate:

```python
# ebay_api_us.py
from ._ebay_api_client import browse_search
from ._filter import is_acceptable

QUERY = "pokemon base set booster box wotc sealed"

def fetch() -> list[dict]:
    rows = browse_search(
        query=QUERY,
        marketplace="EBAY_US",
        filter_expr="price:[15000..],priceCurrency:USD,buyingOptions:{FIXED_PRICE}",
    )
    return [
        {**r, "source": "ebay_api_us"}
        for r in rows
        if is_acceptable(r["title"], r["usd_cents"] / 100.0)
    ]
```

UK mirror: marketplace `EBAY_GB`, query unchanged. Currency on UK comes back as `GBP`. We convert at the source: `usd_cents = round(gbp_amount * usd_per_gbp * 100)` using the FX rate the orchestrator already fetches. To avoid a circular dependency (sources currently know nothing about FX), the UK source accepts an optional `usd_per_gbp` kwarg the same way `ebay_uk.fetch(gbp_per_usd=fx)` does today.

### 3. `scraper/scrape.py` (orchestrator wiring)

Add two new tuples to the existing recent-sales loop... actually no — these are **active listings**, not sales. They belong in the `active_rows` block alongside `ebay_us_active`. Add:

```python
rows = _run_with_timeout("ebay_api_us", lambda: ebay_api_us.fetch())
source_counts["ebay_api_us"] = len(rows)
active_rows.extend(rows)

rows = _run_with_timeout("ebay_api_uk", lambda: ebay_api_uk.fetch(usd_per_gbp=1/fx))
source_counts["ebay_api_uk"] = len(rows)
active_rows.extend(rows)
```

The 90s `SOURCE_TIMEOUT_S` ceiling already wraps each source; API calls take 1-3s so they leave a healthy margin.

### 4. Credentials

**Local dev:**
- `.env` file in repo root (gitignored), loaded via `python-dotenv` at scraper startup. Existing `scraper/requirements.txt` adds `python-dotenv`.
- Or: shell-exported env vars — `python-dotenv`'s `load_dotenv()` no-ops when the file is missing.

**GitHub Actions:**
- Add `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` as repository secrets. User does this themselves via the GitHub Settings UI — I cannot modify repository settings.
- Update `.github/workflows/scrape.yml` to pass them through to the scraper step.

### 5. Tests

- `tests/fixtures/ebay_api_us.json` — captured eBay Browse API response (sanitised — strip any tokens, IDs that aren't relevant).
- `tests/test_source_ebay_api.py` — exercises the normalisation logic against the fixture, no network. Tests:
  - Happy path: 3-row fixture → 3 normalised rows with correct fields.
  - Currency: USD response gives `usd_cents` directly; GBP response with FX rate gives correct converted `usd_cents`.
  - Filter rule: title that fails `is_acceptable` is dropped.
  - Missing seller block: row still emitted with `seller_*` fields as `None`.
- No live-API tests in the suite. Live calls only via a manual `python -m scraper.sources.ebay_api_us` smoke check.

## Data schema

Each row matches the existing snapshot shape exactly so the web UI and `merge_sales` need no changes:

```python
{
    "source": "ebay_api_us",        # or "ebay_api_uk"
    "title": str,                   # itemSummary.title
    "usd_cents": int,               # see currency handling below
    "date": str | None,             # itemSummary.itemCreationDate -> "YYYY-MM-DD" (for active listings)
    "url": str | None,              # itemSummary.itemWebUrl
    "seller_name": str | None,      # itemSummary.seller.username
    "seller_feedback": int | None,  # itemSummary.seller.feedbackScore
    "seller_positive_pct": float | None,  # itemSummary.seller.feedbackPercentage (str -> float)
}
```

Currency:
- US source: `itemSummary.price.value` is a USD string → `usd_cents = round(float(value) * 100)`.
- UK source: `itemSummary.price.value` is a GBP string → `usd_cents = round(float(value) / gbp_per_usd * 100)` using the FX rate the orchestrator already has. This matches what `ebay_uk.py` does today.

## Process: eBay Developer Program signup (Chrome-driven)

Steps I'll drive in your Chrome, stopping for confirmation at each gate:

1. **Navigate to https://developer.ebay.com/**. You sign in with your existing eBay account (I do NOT enter your password — you do).
2. **Join the eBay Developer Program**. Accept the API License Agreement (you click; I read it back to you first).
3. **Create an application keyset** — production. Capture the **App ID (Client ID)** and **Cert ID (Client Secret)** from the resulting page.
4. **You paste the credentials into your terminal**. I write them to `.env` (gitignored) — never logged, never committed.
5. **Submit the Marketplace Insights API access form** at the eBay developer portal. The form asks for business justification — we'll draft a short paragraph framing the use case (personal price-tracking display for a sealed collectible). Approval is uncertain; this is a "send and forget" step.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| eBay returns 401 / token rejected | Token cache wraps in try/except, on 401 we drop the cached token and retry once. Persistent 401 → return `[]` so the snapshot still writes. |
| Rate limit (5k Browse calls/day per app, easy to exceed if cron loops) | 12h cron × 2 marketplaces = 4 calls/day. Far below limit. No retry storm — single attempt per source per run. |
| eBay deprecates Browse API endpoint | Loosely coupled: a single client module means one place to update. Existing SRP scrapers continue working as fallback. |
| Marketplace Insights application rejected | Sold-data path stays on SRP scraping (today's state). No regression. |
| Credentials leak via committed `.env` | `.env` added to `.gitignore`. `.env.example` committed with placeholder values + comment. |
| GitHub Secrets misconfigured (typo, missing) | `_ebay_api_client.py` raises `RuntimeError` on missing creds; orchestrator catches → source returns 0 rows; `source_counts` shows `ebay_api_us=0` so the failure is visible in the snapshot. |

## Out of scope (for this iteration)

- Marketplace Insights API (sold listings). Pending approval — separate design when granted.
- A persistent disk-backed token cache. In-process is enough — the cron runs ~1 minute total per fire, then the process exits. We pay the OAuth round-trip (~200ms) once per fire, which is negligible vs the SRP scrapers' ~25s patchright spin-up.
- Pagination. The Browse API returns up to 200 results per page; for our narrow query 50 is plenty and we never hit the page boundary. If we ever do, the client takes a `limit` param ready to extend.
- Active-listing badge differentiation in the UI (e.g. distinguishing `ebay_us` SRP rows from `ebay_api_us` API rows). The web UI already keys off `source` and will display both; visual treatment can be added later if it matters.

## Tech choices

- **HTTP**: `requests` (already a dependency). No SDK — eBay's official Python SDK (`ebaysdk`) is stale and skews toward the legacy Trading/Finding APIs.
- **Auth**: client_credentials grant. No user-context OAuth needed for public Browse data.
- **Config loading**: `python-dotenv` added to `scraper/requirements.txt`. Loaded once at scraper startup (`scrape.py` top-of-main), no-op if `.env` missing.

## Repo changes summary

```
scraper/
├── sources/
│   ├── _ebay_api_client.py       ← NEW
│   ├── ebay_api_us.py            ← NEW
│   └── ebay_api_uk.py            ← NEW
├── scrape.py                     ← UPDATED: import + wire into active_rows
└── requirements.txt              ← UPDATED: + python-dotenv

.github/workflows/scrape.yml      ← UPDATED: pass EBAY_CLIENT_ID/SECRET env

tests/
├── fixtures/
│   └── ebay_api_us.json          ← NEW
└── test_source_ebay_api.py       ← NEW

.gitignore                        ← UPDATED: + .env
.env.example                      ← NEW
docs/plans/
└── 2026-05-16-ebay-api-source-design.md   ← THIS DOC
```

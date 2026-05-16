# eBay API Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add two new sources (`ebay_api_us`, `ebay_api_uk`) backed by the official eBay Browse API for active-listing data, alongside the existing patchright SRP scrapers.

**Architecture:** Two thin marketplace-specific source modules call a shared transport helper that owns OAuth (client_credentials grant), in-process token caching, and JSON→snapshot-row normalisation. Credentials via env vars from `.env` locally and GitHub Secrets in CI. Sold-listings via Marketplace Insights API is a parallel application that may or may not be approved — not in this plan's code path.

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`, `pytest`. eBay Browse API (`/buy/browse/v1/item_summary/search`).

**Reference design:** [docs/plans/2026-05-16-ebay-api-source-design.md](2026-05-16-ebay-api-source-design.md)

---

## Task ordering rationale

Chrome-driven signup runs first because the captured credentials let us pull real Browse API fixtures, and real fixtures expose response shape quirks (null fields, optional blocks, edge cases) that a synthetic fixture would miss. Once fixtures are in place, the remaining work is straight TDD with no network dependency.

---

## Task 1: Repo housekeeping (.env, .gitignore, python-dotenv)

**Files:**
- Modify: `.gitignore`
- Create: `.env.example`
- Modify: `scraper/requirements.txt`

**Step 1: Read current `.gitignore`**

Run: Read `.gitignore`. Confirm `.env` is not already there.

**Step 2: Add `.env` to `.gitignore`**

Edit `.gitignore` to append (after the existing rules):

```
# Local secrets — never commit
.env
```

**Step 3: Create `.env.example`**

Write `.env.example`:

```
# eBay Developer Program credentials.
# Get these from https://developer.ebay.com/my/keys after creating a Production
# application keyset. Copy this file to .env and fill in real values.
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
```

**Step 4: Add python-dotenv to requirements**

Read `scraper/requirements.txt`. Append `python-dotenv` on a new line (preserve existing entries).

**Step 5: Install locally to verify**

Run: `pip install -r scraper/requirements.txt`
Expected: `python-dotenv` installs without error.

**Step 6: Commit**

```bash
git add .gitignore .env.example scraper/requirements.txt
git commit -m "chore: add .env scaffolding and python-dotenv for eBay API creds"
```

---

## Task 2: Chrome-driven eBay Developer Program signup

**This task is interactive — I drive Chrome, you confirm each step in chat.**

**Files:**
- Create (manually after signup): `.env` (gitignored)

**Step 1: List connected Chrome browsers**

Tool: `mcp__Claude_in_Chrome__list_connected_browsers`
If no browser is connected, stop and ask the user to install/connect the Claude-in-Chrome extension.

**Step 2: Open a fresh MCP tab**

Tool: `mcp__Claude_in_Chrome__tabs_context_mcp` with `createIfEmpty: true`, then `mcp__Claude_in_Chrome__tabs_create_mcp`.

**Step 3: Navigate to developer.ebay.com and pause for user sign-in**

Tool: `mcp__Claude_in_Chrome__navigate` to `https://developer.ebay.com/`.
Wait for the user to confirm they're signed in with their eBay account. **I do NOT enter their password — they do.**

**Step 4: Walk to the API License Agreement**

Use `read_page` / `find` to locate the "Join the eBay Developers Program" or equivalent CTA. Read the agreement summary back to the user. They click Accept.

**Step 5: Create a Production application keyset**

Navigate to the "Application Keys" / "My Account → Keys" page. Click "Create a keyset" → choose Production. The result page displays:
- **App ID (Client ID)**
- **Cert ID (Client Secret)**
- **Dev ID** (not needed for Browse API)

**Step 6: User pastes credentials into the chat**

Pause. Ask the user to copy the Client ID and Client Secret into chat. **Never read them out of the page myself if eBay marks them as sensitive (they may be masked).**

**Step 7: Write `.env`**

Create `.env` in repo root (gitignored, so safe):

```
EBAY_CLIENT_ID=<value pasted by user>
EBAY_CLIENT_SECRET=<value pasted by user>
```

**Step 8: Verify token endpoint works**

Run:
```bash
python -c "
import os, base64, requests
from dotenv import load_dotenv
load_dotenv()
auth = base64.b64encode(f\"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}\".encode()).decode()
r = requests.post(
    'https://api.ebay.com/identity/v1/oauth2/token',
    headers={'Authorization': f'Basic {auth}', 'Content-Type': 'application/x-www-form-urlencoded'},
    data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'},
    timeout=15,
)
print(r.status_code)
print('access_token' in r.json())
"
```

Expected output:
```
200
True
```

If 401: credentials wrong, return to step 6. If anything else: stop and debug before continuing.

**Step 9: Submit Marketplace Insights API application (best-effort)**

Navigate to the Marketplace Insights API page on developer.ebay.com. Locate the access-request form. Fill the business-justification field together with the user (short paragraph: "Personal price-tracking display for a single sealed Pokémon Base Set Booster Box. Read-only, low volume — one query per marketplace per 12h cron"). User submits the form. Note the application status link if shown.

**No commit** — `.env` is gitignored.

---

## Task 3: Capture a real Browse API response fixture

**Files:**
- Create: `tests/fixtures/ebay_browse_us.json`
- Create: `tests/fixtures/ebay_browse_uk.json`

**Step 1: Capture US response**

Run:
```bash
python -c "
import os, base64, json, requests
from dotenv import load_dotenv
load_dotenv()
auth = base64.b64encode(f\"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}\".encode()).decode()
tok = requests.post(
    'https://api.ebay.com/identity/v1/oauth2/token',
    headers={'Authorization': f'Basic {auth}', 'Content-Type': 'application/x-www-form-urlencoded'},
    data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'},
    timeout=15,
).json()['access_token']
r = requests.get(
    'https://api.ebay.com/buy/browse/v1/item_summary/search',
    headers={'Authorization': f'Bearer {tok}', 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'},
    params={'q': 'pokemon base set booster box wotc sealed', 'filter': 'price:[15000..],priceCurrency:USD,buyingOptions:{FIXED_PRICE}', 'limit': 50},
    timeout=20,
)
print(r.status_code)
open('tests/fixtures/ebay_browse_us.json', 'w').write(json.dumps(r.json(), indent=2))
"
```

Expected: status 200, file written.

**Step 2: Capture UK response**

Repeat with `X-EBAY-C-MARKETPLACE-ID: EBAY_GB` and `priceCurrency:GBP`. Write to `tests/fixtures/ebay_browse_uk.json`.

**Step 3: Sanitise fixtures**

Read each fixture. Search for and redact: any `legacyItemId`/`itemId` values longer than ~30 chars that look like internal IDs (leave the structure, replace value with a placeholder like `"v1|123456|0"`). Leave titles, prices, seller usernames intact — these are public-listing data.

**Step 4: Commit fixtures**

```bash
git add tests/fixtures/ebay_browse_us.json tests/fixtures/ebay_browse_uk.json
git commit -m "test: add captured eBay Browse API fixtures (US + UK)"
```

---

## Task 4: `_ebay_api_client.py` — OAuth + browse_search (TDD)

**Files:**
- Test: `tests/test_source_ebay_api.py`
- Create: `scraper/sources/_ebay_api_client.py`

**Step 1: Write the failing test for response normalisation**

Create `tests/test_source_ebay_api.py`:

```python
"""Tests for the eBay Browse API client and the two marketplace sources.

We never hit the live API in tests — all fixtures are captured JSON
responses in tests/fixtures/. Token caching is exercised via a fake
clock so we don't sleep.
"""
import json
from pathlib import Path

import pytest

from scraper.sources._ebay_api_client import _normalise_response

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_normalise_us_response_returns_expected_shape():
    payload = _load("ebay_browse_us.json")
    rows = _normalise_response(payload, currency="USD")

    # Fixture has N items; assert against the first one's required fields
    assert len(rows) > 0
    row = rows[0]
    assert set(row.keys()) >= {
        "title", "usd_cents", "date", "url",
        "seller_name", "seller_feedback", "seller_positive_pct",
    }
    assert isinstance(row["usd_cents"], int)
    assert row["usd_cents"] > 0
    assert isinstance(row["title"], str) and row["title"]


def test_normalise_uk_response_converts_gbp_to_usd_cents():
    payload = _load("ebay_browse_uk.json")
    gbp_per_usd = 0.75  # 1 USD = 0.75 GBP
    rows = _normalise_response(payload, currency="GBP", gbp_per_usd=gbp_per_usd)

    assert len(rows) > 0
    row = rows[0]
    # Spot-check the conversion: usd_cents = gbp_value / gbp_per_usd * 100
    raw_gbp = float(payload["itemSummaries"][0]["price"]["value"])
    expected = round(raw_gbp / gbp_per_usd * 100)
    assert row["usd_cents"] == expected


def test_normalise_handles_missing_seller_block():
    # Synthetic minimal payload — itemSummaries with no seller key
    payload = {
        "itemSummaries": [
            {
                "title": "Pokemon Base Set Booster Box WOTC Sealed",
                "price": {"value": "30000.00", "currency": "USD"},
                "itemWebUrl": "https://www.ebay.com/itm/123",
                "itemCreationDate": "2026-05-10T12:00:00.000Z",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert len(rows) == 1
    assert rows[0]["seller_name"] is None
    assert rows[0]["seller_feedback"] is None
    assert rows[0]["seller_positive_pct"] is None


def test_normalise_skips_items_with_missing_price():
    payload = {
        "itemSummaries": [
            {"title": "No price", "itemWebUrl": "https://x"},
            {"title": "Has price", "price": {"value": "25000.00", "currency": "USD"}, "itemWebUrl": "https://y"},
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert len(rows) == 1
    assert rows[0]["title"] == "Has price"


def test_normalise_parses_item_creation_date():
    payload = {
        "itemSummaries": [
            {
                "title": "Test",
                "price": {"value": "20000.00", "currency": "USD"},
                "itemWebUrl": "https://x",
                "itemCreationDate": "2026-05-10T12:00:00.000Z",
            }
        ]
    }
    rows = _normalise_response(payload, currency="USD")
    assert rows[0]["date"] == "2026-05-10"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_source_ebay_api.py -v`
Expected: All tests fail with `ImportError: cannot import name '_normalise_response' from 'scraper.sources._ebay_api_client'`.

**Step 3: Implement `_normalise_response`**

Create `scraper/sources/_ebay_api_client.py`:

```python
"""eBay Browse API transport helper.

Mirrors the role of :mod:`scraper.sources._browser` — a shared transport
that does HTTP + response normalisation, but no query-specific parsing.
Two thin marketplace sources (``ebay_api_us`` and ``ebay_api_uk``) call
:func:`browse_search` with their own query and filter.

Auth model: OAuth Application Token (client_credentials grant). The
Browse API only needs the public ``https://api.ebay.com/oauth/api_scope``
scope. Tokens are valid for ~2h; we cache in-process with a 60s safety
margin, so a cron run that fires multiple sources only pays one OAuth
round-trip (~200ms) total.

Failure mode: any exception (network, 401, malformed JSON) is caught by
the caller (the source module), which returns ``[]`` so the orchestrator
records the source as 0 rows rather than crashing the snapshot.
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import sys
import time
from typing import Any

import requests

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_TOKEN_SCOPE = "https://api.ebay.com/oauth/api_scope"

# (access_token, expires_at_epoch). None means "not yet fetched".
_cached_token: tuple[str, float] | None = None


def _get_token(timeout: int = 15) -> str:
    """Return a valid OAuth Application Token, refreshing if needed.

    Cached in-process for the remainder of its declared lifetime minus
    a 60s safety margin. Subsequent calls within that window return the
    cached value without hitting the token endpoint.
    """
    global _cached_token
    now = time.time()
    if _cached_token and _cached_token[1] > now + 60:
        return _cached_token[0]

    client_id = os.environ.get("EBAY_CLIENT_ID")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set — see .env.example"
        )

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": _TOKEN_SCOPE},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    token = body["access_token"]
    expires_at = now + float(body.get("expires_in", 7200))
    _cached_token = (token, expires_at)
    return token


def _parse_item_creation_date(raw: str | None) -> str | None:
    """Convert eBay's ISO timestamp ("2026-05-10T12:00:00.000Z") to "YYYY-MM-DD"."""
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except (ValueError, TypeError):
        return None


def _parse_feedback_pct(raw: Any) -> float | None:
    """eBay returns feedbackPercentage as a string like '99.5'. Parse to float."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_feedback_count(raw: Any) -> int | None:
    """feedbackScore is normally an int; defensive parse anyway."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _normalise_response(
    payload: dict,
    currency: str,
    gbp_per_usd: float | None = None,
) -> list[dict]:
    """Convert a Browse API response payload to snapshot-row dicts.

    Skips items missing a parseable price. ``source`` is NOT set here —
    the caller (US or UK source module) tags rows so the orchestrator
    can attribute counts. ``date`` is the listing's creation date for
    active listings (Browse API surfaces no separate sale date).

    For GBP responses the caller passes ``gbp_per_usd`` (the FX rate
    the orchestrator already fetched) so we can populate ``usd_cents``
    in the canonical USD-cents shape the rest of the pipeline uses.
    """
    out: list[dict] = []
    for item in payload.get("itemSummaries") or []:
        price = item.get("price")
        if not price or "value" not in price:
            continue
        try:
            raw_val = float(price["value"])
        except (ValueError, TypeError):
            continue
        if currency == "USD":
            usd_cents = round(raw_val * 100)
        elif currency == "GBP":
            if not gbp_per_usd:
                continue
            usd_cents = round(raw_val / gbp_per_usd * 100)
        else:
            continue

        seller = item.get("seller") or {}
        out.append({
            "title": (item.get("title") or "").strip(),
            "usd_cents": usd_cents,
            "date": _parse_item_creation_date(item.get("itemCreationDate")),
            "url": item.get("itemWebUrl"),
            "seller_name": seller.get("username"),
            "seller_feedback": _parse_feedback_count(seller.get("feedbackScore")),
            "seller_positive_pct": _parse_feedback_pct(seller.get("feedbackPercentage")),
        })
    return out


def browse_search(
    query: str,
    marketplace: str,
    filter_expr: str | None = None,
    limit: int = 50,
    currency: str = "USD",
    gbp_per_usd: float | None = None,
    timeout: int = 20,
) -> list[dict]:
    """Run a single Browse API search and return normalised rows.

    Parameters
    ----------
    query: search keywords (``q=`` param).
    marketplace: ``"EBAY_US"`` or ``"EBAY_GB"`` — sent as the
        ``X-EBAY-C-MARKETPLACE-ID`` header.
    filter_expr: eBay's filter mini-language, e.g.
        ``"price:[15000..],priceCurrency:USD,buyingOptions:{FIXED_PRICE}"``.
    limit: max items per page (Browse caps at 200; 50 is plenty here).
    currency: expected currency code, used for normalisation.
    gbp_per_usd: required when currency is ``"GBP"`` so prices land in
        ``usd_cents``.
    timeout: HTTP request timeout in seconds.
    """
    token = _get_token()
    params: dict[str, Any] = {"q": query, "limit": str(limit)}
    if filter_expr:
        params["filter"] = filter_expr
    r = requests.get(
        _SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
        },
        params=params,
        timeout=timeout,
    )
    # On 401 the cached token is dead (revoked, rotated). Clear cache and
    # retry once; subsequent failures bubble up to the source's try/except.
    if r.status_code == 401:
        global _cached_token
        _cached_token = None
        token = _get_token()
        r = requests.get(
            _SEARCH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
            },
            params=params,
            timeout=timeout,
        )
    r.raise_for_status()
    return _normalise_response(r.json(), currency=currency, gbp_per_usd=gbp_per_usd)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_source_ebay_api.py -v`
Expected: all 5 tests pass.

**Step 5: Commit**

```bash
git add scraper/sources/_ebay_api_client.py tests/test_source_ebay_api.py
git commit -m "feat: add eBay Browse API transport helper with OAuth + normalisation"
```

---

## Task 5: `ebay_api_us.py` (TDD)

**Files:**
- Test: `tests/test_source_ebay_api.py` (extend)
- Create: `scraper/sources/ebay_api_us.py`

**Step 1: Append failing test for `ebay_api_us.fetch`'s filter behaviour**

Append to `tests/test_source_ebay_api.py`:

```python
def test_ebay_api_us_drops_titles_rejected_by_filter(monkeypatch):
    """The source must run is_acceptable on every row from the client."""
    from scraper.sources import ebay_api_us

    # Replace the transport with a stub that returns two rows: one with a
    # title is_acceptable will accept, one it will reject (e.g. mentions
    # "japanese" — see _filter.py for the rejection rules).
    def fake_browse_search(**kwargs):
        return [
            {
                "title": "Pokemon Base Set Booster Box WOTC Sealed",
                "usd_cents": 3_500_000,
                "date": "2026-05-10",
                "url": "https://www.ebay.com/itm/1",
                "seller_name": "seller_a", "seller_feedback": 100, "seller_positive_pct": 99.5,
            },
            {
                "title": "Pokemon Japanese Base Set Booster Box Sealed",
                "usd_cents": 200_000,
                "date": "2026-05-10",
                "url": "https://www.ebay.com/itm/2",
                "seller_name": "seller_b", "seller_feedback": 50, "seller_positive_pct": 100.0,
            },
        ]
    monkeypatch.setattr(ebay_api_us, "browse_search", fake_browse_search)

    rows = ebay_api_us.fetch()
    assert len(rows) == 1
    assert rows[0]["source"] == "ebay_api_us"
    assert "japanese" not in rows[0]["title"].lower()
```

Before writing the source, glance at `scraper/sources/_filter.py` to confirm the rejection example holds. If `is_acceptable` doesn't reject the Japanese title at the chosen price, pick another rejection case from `_filter.py` and adjust the test.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_source_ebay_api.py::test_ebay_api_us_drops_titles_rejected_by_filter -v`
Expected: FAIL with `ImportError: cannot import name 'ebay_api_us'`.

**Step 3: Implement `ebay_api_us.py`**

Create `scraper/sources/ebay_api_us.py`:

```python
"""eBay US active-listings source via the official Browse API.

Sibling to ``scraper.sources.ebay_us_active`` (which scrapes the
SRP via patchright). Runs alongside, not as a replacement — if the
API path breaks (token revoked, eBay deprecates the endpoint) the
SRP scraper still feeds the snapshot, and vice-versa.

Output shape matches the existing snapshot row contract exactly; see
:func:`scraper.sources._ebay_api_client._normalise_response`. We add
the ``source`` tag here so the orchestrator's ``source_counts`` and
the web UI's per-source badging both pick it up.
"""
from __future__ import annotations

from ._ebay_api_client import browse_search
from ._filter import is_acceptable

QUERY = "pokemon base set booster box wotc sealed"
FILTER = "price:[15000..],priceCurrency:USD,buyingOptions:{FIXED_PRICE}"


def fetch() -> list[dict]:
    """Return active-listing rows from eBay US.

    Errors (missing creds, network, 401) propagate to the caller, which
    in the orchestrator is wrapped in ``_run_with_timeout`` and gets
    converted to ``[]`` automatically.
    """
    rows = browse_search(
        query=QUERY,
        marketplace="EBAY_US",
        filter_expr=FILTER,
        currency="USD",
    )
    return [
        {**r, "source": "ebay_api_us"}
        for r in rows
        if is_acceptable(r["title"], r["usd_cents"] / 100.0)
    ]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_source_ebay_api.py -v`
Expected: all tests pass (including the new one).

**Step 5: Smoke test against live API**

Run:
```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from scraper.sources import ebay_api_us
rows = ebay_api_us.fetch()
print(f'{len(rows)} rows')
for r in rows[:3]:
    print(f'  ${r[\"usd_cents\"]/100:.0f} — {r[\"title\"][:60]}')
"
```

Expected: non-zero row count, prices in plausible range (typically $15k–$60k for the WOTC sealed query). If 0 rows: the filter may be too tight for current listings; that's fine — log the response shape and continue. If error: stop and debug.

**Step 6: Commit**

```bash
git add scraper/sources/ebay_api_us.py tests/test_source_ebay_api.py
git commit -m "feat: add ebay_api_us source backed by Browse API"
```

---

## Task 6: `ebay_api_uk.py` (TDD)

**Files:**
- Test: `tests/test_source_ebay_api.py` (extend)
- Create: `scraper/sources/ebay_api_uk.py`

**Step 1: Append failing test for the UK source**

Append to `tests/test_source_ebay_api.py`:

```python
def test_ebay_api_uk_converts_gbp_via_fx_rate(monkeypatch):
    from scraper.sources import ebay_api_uk

    captured = {}

    def fake_browse_search(**kwargs):
        captured.update(kwargs)
        # Return a row already normalised — _ebay_api_client did the conversion.
        return [
            {
                "title": "Pokemon Base Set Booster Box WOTC Sealed",
                "usd_cents": 4_000_000,  # 30000 GBP / 0.75 GBP/USD * 100
                "date": "2026-05-10",
                "url": "https://www.ebay.co.uk/itm/1",
                "seller_name": "uk_seller", "seller_feedback": 200, "seller_positive_pct": 99.0,
            },
        ]
    monkeypatch.setattr(ebay_api_uk, "browse_search", fake_browse_search)

    rows = ebay_api_uk.fetch(gbp_per_usd=0.75)
    assert captured["marketplace"] == "EBAY_GB"
    assert captured["currency"] == "GBP"
    assert captured["gbp_per_usd"] == 0.75
    assert len(rows) == 1
    assert rows[0]["source"] == "ebay_api_uk"


def test_ebay_api_uk_returns_empty_when_fx_unavailable(monkeypatch):
    from scraper.sources import ebay_api_uk

    # No GBP-per-USD rate → source can't convert, must short-circuit to [].
    rows = ebay_api_uk.fetch(gbp_per_usd=None)
    assert rows == []
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_source_ebay_api.py -v -k uk`
Expected: FAIL on `ImportError: cannot import name 'ebay_api_uk'`.

**Step 3: Implement `ebay_api_uk.py`**

Create `scraper/sources/ebay_api_uk.py`:

```python
"""eBay UK active-listings source via the official Browse API.

Sibling to ``scraper.sources.ebay_uk`` (SRP scraper). The UK marketplace
returns prices in GBP — we convert to USD-cents at the transport layer
using the FX rate the orchestrator already fetched, so every row in the
snapshot lives in the same canonical currency the rest of the pipeline
assumes.

If the orchestrator's FX fetch failed and there's no rate to pass, the
source short-circuits to ``[]`` — we can't honestly emit USD-cents
without a rate, and silently mixing GBP-valued rows would corrupt the
downstream averages and "from £X" summary line.
"""
from __future__ import annotations

from ._ebay_api_client import browse_search
from ._filter import is_acceptable

# UK uses the same query — the keywords are equally valid on either
# marketplace. Filter switches to GBP and lifts the floor slightly: UK
# vintage stock is rarer so a £10k cutoff still excludes reprints
# without losing genuine Unlimited boxes.
QUERY = "pokemon base set booster box wotc sealed"
FILTER = "price:[10000..],priceCurrency:GBP,buyingOptions:{FIXED_PRICE}"


def fetch(gbp_per_usd: float | None = None) -> list[dict]:
    """Return active-listing rows from eBay UK.

    Parameters
    ----------
    gbp_per_usd: FX rate from the orchestrator — the value
        ``scraper.fx.fetch_usd_to_gbp()`` returns, i.e. GBP per 1 USD
        (e.g. ``0.7389``). The orchestrator should pass ``fx`` directly,
        the same way ``ebay_uk.fetch(gbp_per_usd=fx)`` does. Required —
        if missing or non-positive, the source returns ``[]`` rather
        than emit rows we can't convert.
    """
    if not gbp_per_usd:
        return []
    rows = browse_search(
        query=QUERY,
        marketplace="EBAY_GB",
        filter_expr=FILTER,
        currency="GBP",
        gbp_per_usd=gbp_per_usd,
    )
    return [
        {**r, "source": "ebay_api_uk"}
        for r in rows
        if is_acceptable(r["title"], r["usd_cents"] / 100.0)
    ]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_source_ebay_api.py -v`
Expected: all tests pass.

**Step 5: Smoke test against live API**

Run:
```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from scraper.sources import ebay_api_uk
rows = ebay_api_uk.fetch(gbp_per_usd=0.75)
print(f'{len(rows)} rows')
for r in rows[:3]:
    print(f'  USD ${r[\"usd_cents\"]/100:.0f} — {r[\"title\"][:60]}')
"
```

Expected: non-zero row count (UK has lower liquidity for this item — 0 is also a plausible result on a quiet day, that's fine). No exceptions.

**Step 6: Commit**

```bash
git add scraper/sources/ebay_api_uk.py tests/test_source_ebay_api.py
git commit -m "feat: add ebay_api_uk source with GBP→USD conversion"
```

---

## Task 7: Wire into `scrape.py` orchestrator

**Files:**
- Modify: `scraper/scrape.py`

**Step 1: Load .env at scraper startup**

Read `scraper/scrape.py`. At the top of the imports block, add:

```python
from dotenv import load_dotenv
load_dotenv()  # noop in CI where vars come from GitHub Secrets
```

**Step 2: Import the new sources**

Find the existing import line:

```python
from .sources import ebay_uk, ebay_us, ebay_us_active
```

Replace with:

```python
from .sources import ebay_uk, ebay_us, ebay_us_active, ebay_api_us, ebay_api_uk
```

**Step 3: Add API sources to the active-listings block**

Find the `active_rows: list[dict] = []` block (around line 183). After the existing `ebay_us_active` retry block but before any subsequent code, append:

```python
    # API-backed active listings. Cheap (~1-3s each) and resilient — runs
    # alongside the SRP scrapers so either path can fail without dropping
    # the snapshot to zero rows. ebay_api_uk needs the FX rate to convert
    # GBP → USD-cents; fx is already GBP-per-USD so we pass it directly.
    rows = _run_with_timeout("ebay_api_us", lambda: ebay_api_us.fetch())
    source_counts["ebay_api_us"] = len(rows)
    active_rows.extend(rows)

    rows = _run_with_timeout("ebay_api_uk", lambda: ebay_api_uk.fetch(gbp_per_usd=fx))
    source_counts["ebay_api_uk"] = len(rows)
    active_rows.extend(rows)
```

**Step 4: Run the existing test suite**

Run: `python -m pytest -v`
Expected: all tests pass (no regression in scraper internals).

**Step 5: Local end-to-end smoke run**

Run: `python -m scraper.scrape`
Expected:
- Exit code 0.
- Console contains lines like `INFO: source ebay_api_us returned N rows in <3s` and same for `ebay_api_uk`.
- `data/snapshot.json` updated: `source_counts` now has `ebay_api_us` and `ebay_api_uk` keys, `active_listings` array contains rows tagged with those sources.

If `ebay_api_*` returned 0 with no error: that's acceptable for a "no current listings match the filter" day. Re-run once. Persistent 0 with no error means the filter is too restrictive — revisit the `FILTER` constants.

**Step 6: Commit**

```bash
git add scraper/scrape.py
git commit -m "feat: wire ebay_api_us + ebay_api_uk into orchestrator"
```

---

## Task 8: GitHub Actions workflow update

**Files:**
- Modify: `.github/workflows/scrape.yml`

**Step 1: Read the workflow**

Read `.github/workflows/scrape.yml`. Locate the step that runs `python -m scraper.scrape`.

**Step 2: Add env vars to the scraper step**

Add an `env:` block to the scraper-running step (or extend an existing one) so the secrets reach the process:

```yaml
      - name: Run scraper
        env:
          EBAY_CLIENT_ID: ${{ secrets.EBAY_CLIENT_ID }}
          EBAY_CLIENT_SECRET: ${{ secrets.EBAY_CLIENT_SECRET }}
        run: python -m scraper.scrape
```

(If the step already has an `env:` block, append the two new keys without removing existing ones.)

**Step 3: Tell the user to set the secrets**

**This step is manual — the user must do it.** I cannot modify repository settings.

Tell the user:
> Add these two secrets to the repository at GitHub → Settings → Secrets and variables → Actions → New repository secret:
> - `EBAY_CLIENT_ID` = your eBay App ID (Client ID)
> - `EBAY_CLIENT_SECRET` = your eBay Cert ID (Client Secret)

Wait for confirmation before continuing.

**Step 4: Commit the workflow change**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci: pass eBay API credentials to scraper from GitHub Secrets"
```

**Step 5: Manually trigger the workflow**

The user goes to GitHub → Actions → "Scrape" workflow → "Run workflow" (workflow_dispatch). Wait for the run to finish.

**Step 6: Verify the run**

Open the run logs. Confirm:
- Both `ebay_api_us` and `ebay_api_uk` appear in the source-count summary.
- No `EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set` error.

Pull the latest commit (the cron's `chore: snapshot ...` commit). Check `data/snapshot.json` has the new sources in `source_counts`.

If anything fails: read the run log, identify the failing step, fix, push. Re-trigger.

---

## Task 9: Verification + finish

**Step 1: Run the full test suite one more time**

Run: `python -m pytest -v`
Expected: all tests pass.

**Step 2: Confirm no secrets committed**

Run: `git log --all -p -- .env` (should show no history). Run: `git diff main..HEAD --stat` and scan for unexpected files.

**Step 3: Finish-the-branch workflow**

Invoke `superpowers:finishing-a-development-branch` to decide on merge / PR / cleanup.

---

## Notes for the executing agent

- **Skill-check at the start of each task.** Use `superpowers:test-driven-development` for code tasks (3–7) and `superpowers:verification-before-completion` before any commit that claims a task is done.
- **Marketplace Insights API.** Task 2 step 9 submits an application — but the result lands days/weeks later and is out of scope for this plan. If approved, a separate design + plan will add a sold-listings API source.
- **`.env` must never appear in `git status` after Task 2.** If it does, the `.gitignore` change from Task 1 didn't land — fix before continuing.
- **The Chrome workflow is interactive.** Each Chrome step (Task 2) must pause for user confirmation. Do not auto-click "Accept" on agreements, do not enter passwords, do not navigate past confirmation gates without the user saying so in chat.
- **If `is_acceptable` rejection example in Task 5 doesn't actually reject:** glance at `scraper/sources/_filter.py` and pick a real rejection case. The test exists to prove the filter is being applied, not to enshrine a specific rejection rule.

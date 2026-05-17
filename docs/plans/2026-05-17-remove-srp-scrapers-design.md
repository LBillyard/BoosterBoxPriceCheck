# Remove SRP Scrapers — Design

**Date:** 2026-05-17
**Owner:** LBillyard

## Goal

Delete the patchright SRP scrapers (eBay UK/US sold + active, 130point) and their shared headless-browser transport. The Browse API source ([BoosterBoxPriceCheck#1](https://github.com/LBillyard/BoosterBoxPriceCheck/pull/1)) has replaced them; the SRP path consistently returns 0 rows from GitHub Actions IPs because eBay's bot detection refuses datacenter-IP traffic. Keeping the SRP code adds ~3 minutes of cron runtime per 12h cycle for zero rows.

## Scope

**Delete:**

- `scraper/sources/ebay_uk.py` (SRP sold UK)
- `scraper/sources/ebay_us.py` (SRP sold US)
- `scraper/sources/ebay_us_active.py` (SRP active US)
- `scraper/sources/ebay_uk_active.py` (SRP active UK — was already imported-out in `scrape.py`)
- `scraper/sources/ebay_pinned.py` (SRP item-page fallback — already imported-out)
- `scraper/sources/onethirtypoint.py` (130point sold listings — already imported-out)
- `scraper/sources/_browser.py` (patchright transport, sole consumer was the SRP set)
- `scraper/sources/_ebay_item.py` (item-page helper, used only by `ebay_us_active`)
- `tests/test_source_ebay_uk.py`, `tests/test_source_ebay_us.py`, `tests/test_source_ebay_active.py`, `tests/test_source_130point.py`
- `tests/fixtures/130point.html`, `tests/fixtures/ebay_uk.html`, `tests/fixtures/ebay_uk_synthetic.html`, `tests/fixtures/ebay_us.html`

**Modify:**

- `scraper/scrape.py` — remove imports for the deleted sources, remove the SOURCE_TIMEOUT_S-wrapped fetch loop entries for them, simplify the orchestrator (the API sources don't need 90s timeouts since calls take ~1-3 s).
- `scraper/requirements.txt` — drop `patchright==1.58.2`.
- `.github/workflows/scrape.yml` — drop the "Install patchright Chromium" step.
- `tests/fixtures/README.md` — drop the HTML-fixtures paragraph.

**Keep:**

- `scraper/sources/_filter.py` — the API sources call `is_acceptable`.
- `scraper/sources/_ebay_api_client.py`, `ebay_api_us.py`, `ebay_api_uk.py` — the live path.
- `scraper/parser.py` and `tests/fixtures/booster_box.html` — PriceCharting parsing is still alive.
- `scraper/fx.py`, `scraper/history.py`, `scraper/snapshot.py` — used by the live pipeline.
- All other tests (filter, fx, history, parser, snapshot, ebay_api).

## Risks

- **Existing PriceCharting "Last Sold" depends on `parser.py` + `fx.py`** — neither touched. Verified by grep.
- **Snapshot schema unchanged** — `source_counts` will lose the SRP keys (`ebay_uk`, `ebay_us`, `ebay_us_active`) but the web UI's `renderSources` array tolerates missing keys (filter line `keys = order.filter(k => k in all)`).
- **Source-of-truth fallback gone** — if the API path breaks (token revoked, eBay outage), the cron writes 0 active listings until fixed. Acceptable: the SRP fallback was already 0 in practice.
- **Cron runtime** drops to ~30 s (just PriceCharting + 2 API calls). Should still be well within the 12 min workflow ceiling.

## Out of scope

- API-listings history persistence (separate PR B, dedup by itemId + usd_cents).
- Marketplace Insights API application (separate workflow once approved).
- Touching the web UI — already updated to recognise `ebay_api_*` source names in PR #1.

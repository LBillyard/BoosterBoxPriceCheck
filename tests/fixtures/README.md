# Test fixtures

## HTML fixtures (SRP-scraper tests)

`130point.html`, `booster_box.html`, `ebay_uk.html`, `ebay_uk_synthetic.html`, and
`ebay_us.html` are real or partially-synthetic HTML captures used by the existing
SRP-scraper tests (`tests/test_source_130point.py`, `tests/test_source_ebay_us.py`,
`tests/test_source_ebay_uk.py`, `tests/test_source_ebay_active.py`).

## eBay Browse API fixtures

`ebay_browse_us.json` and `ebay_browse_uk.json` are **real** captures of
`GET /buy/browse/v1/item_summary/search` against the Production Browse API,
captured **2026-05-17** with the queries the production sources use
(`scraper/sources/ebay_api_us.py` and `scraper/sources/ebay_api_uk.py`).

Synthetic fixtures (committed 2026-05-16) lived here briefly while the eBay
Developer Program account was in manual review. They were replaced once the
account was approved and a Production keyset was issued.

The fixtures contain only public listing data (titles, prices, item URLs, public
seller usernames + feedback counts) — no tokens, no PII. Refreshing them is safe;
follow the capture command in `docs/plans/2026-05-16-ebay-api-source.md` Task 3.
The unit tests assert only on shape and on the first-item conversion math, not
on specific item content, so re-captures don't routinely require test changes.

### Edge cases worth knowing about

The unit tests cover a few cases the real fixtures may or may not contain on any
given day. To keep coverage stable, the following tests use inline synthetic
payloads instead of the JSON fixtures:

- Missing `seller` block — parser must emit `None` for seller fields.
- `"Japanese"` in the title — `is_acceptable` filter must reject.
- Items missing `price.value` — normaliser must skip.
- Items with `feedbackPercentage` as a string (eBay's documented shape).
- Out-of-band currencies and missing/negative FX rates — raise `ValueError`.

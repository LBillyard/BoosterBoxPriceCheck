# Test fixtures

## HTML fixtures (SRP-scraper tests)

`130point.html`, `booster_box.html`, `ebay_uk.html`, `ebay_uk_synthetic.html`, and
`ebay_us.html` are real or partially-synthetic HTML captures used by the existing
SRP-scraper tests (`tests/test_source_130point.py`, `tests/test_source_ebay_us.py`,
`tests/test_source_ebay_uk.py`, `tests/test_source_ebay_active.py`).

## eBay Browse API fixtures (synthetic)

`ebay_browse_us.json` and `ebay_browse_uk.json` are **synthetic** Browse API
responses created **2026-05-16** because the eBay Developer Program account is
pending approval (manual review, ~1 business day). They were hand-crafted to
match the documented shape of
`GET /buy/browse/v1/item_summary/search` responses
(https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search)
so downstream code (Tasks 4-7) can be built and unit-tested without live
credentials.

**These should be replaced with real captures** once the eBay Developer Program
approval lands and credentials are available. Re-capture them following the
original Task 3 procedure in `docs/plans/2026-05-16-ebay-api-source.md`, then
update tests if any real-response field shape diverges from the synthetic
versions.

### Edge cases encoded in the synthetic fixtures

`ebay_browse_us.json` deliberately exercises these cases so the downstream
parser/filter pair (Tasks 4-5) gets coverage:

- An item with **no `seller` block** (parser must produce `None` for the seller
  fields rather than crash).
- An item with `"Japanese"` in the title (the `is_acceptable` filter must reject
  it even though the price is in-range).

`ebay_browse_uk.json` uses GBP-quoted prices and includes a seller with
`feedbackPercentage` of `"100.0"` (a string, not a bare float) to mirror eBay's
documented response format.

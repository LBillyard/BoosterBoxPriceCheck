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

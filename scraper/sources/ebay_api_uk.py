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

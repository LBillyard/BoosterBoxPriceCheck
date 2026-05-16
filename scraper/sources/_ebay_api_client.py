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

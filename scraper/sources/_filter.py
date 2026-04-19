"""Shared listing/title filter for sealed Base Set Booster Box (Unlimited).

The collector tracks the *Unlimited* edition only. Listings on aggregator
sites routinely conflate three superficially similar boxes:

* 1st Edition  (~$300k+)  — title says "1st Ed" / "First Edition"
* Shadowless   (~$80–150k) — title says "Shadowless" / "No Shadow"
* Unlimited    (~$30–45k) — the target; no edition stamp

If a 1st Edition slips through into the snapshot it inflates the displayed
value massively, so this filter is the safety net. It combines a title
allow/deny check with a sanity price band.
"""
from __future__ import annotations

import re

# Edition keywords that disqualify the listing outright.
EXCLUDE_RE = re.compile(
    r"\b(1st\s*ed(?:ition)?|first\s*edition|shadowless|no[- ]shadow)\b",
    re.I,
)

# Plausible USD price range for a sealed Unlimited Base Set Booster Box.
# Anything outside this band is rejected even if the title looks fine — it
# suggests a mislabelled 1st Edition (too high) or wrong product (too low).
PRICE_BAND_USD = (15_000, 80_000)

# Title must mention Base Set + booster/sealed box. This rejects single packs,
# mixed lots, Jungle/Fossil/etc. boxes, and unrelated cards.
TITLE_REQUIRE_RE = re.compile(
    r"\bbase\s*set\b.*\b(booster\s*box|sealed\s*box)\b",
    re.I,
)


def is_acceptable(title: str, usd: float) -> bool:
    """Return True iff this listing plausibly matches an Unlimited Base Set
    Booster Box, sealed, in a sane price range."""
    if title is None:
        return False
    if EXCLUDE_RE.search(title):
        return False
    if not TITLE_REQUIRE_RE.search(title):
        return False
    return PRICE_BAND_USD[0] <= usd <= PRICE_BAND_USD[1]

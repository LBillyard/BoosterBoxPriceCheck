"""Shared listing/title filter for sealed Base Set Booster Box (Unlimited).

The collector tracks the *Unlimited* edition only. Listings on aggregator
sites routinely conflate several superficially similar boxes:

* 1st Edition   (~$300k+)  — title says "1st Ed" / "First Edition"
* Shadowless    (~$80-150k) — title says "Shadowless" / "No Shadow"
* Unlimited     (~$30-45k) — the target; no edition stamp
* Base Set 2    (~$10-20k)  — 2000 reprint, "Base Set 2" in title
* Mega Evolution / Scarlet & Violet / Sword & Shield "Base Set" — modern
  reprints; cheap but the parser would happily match the substring "Base
  Set" if not explicitly excluded.

If a 1st Edition or any reprint slips through into the snapshot it skews
the displayed value, so this filter is the safety net. It combines a title
allow/deny check with a sanity price band. Foreign-language vintage boxes
(Spanish/French/German "Base Set") are also excluded — the user tracks
the English Unlimited print specifically.
"""
from __future__ import annotations

import re

# Edition / variant keywords that disqualify the listing outright.
# "base set 2" is a separate, much-cheaper SKU.
# "mega evolution" / "scarlet" / "sword" / "shield" / "sun" / "moon" /
# "crown zenith" / "151" all mark modern Pokemon TCG sets that sometimes
# carry "Base Set" in their marketing name.
EXCLUDE_RE = re.compile(
    r"\b("
    r"1st\s*ed(?:ition)?|first\s*edition|"
    r"shadowless|no[- ]shadow|"
    r"base\s*set\s*2|"
    r"mega\s*evolution|"
    r"scarlet|sword|shield|crown\s*zenith|"
    r"151|"
    r"spanish|french|german|italian|japanese|portuguese|"
    r"empty|theme\s*deck|booster\s*pack|single\s*pack"
    r")\b",
    re.I,
)

# Plausible USD price range for a sealed Unlimited Base Set Booster Box.
# Anything outside this band is rejected even if the title looks fine - it
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

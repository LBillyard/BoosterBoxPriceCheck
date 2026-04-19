from scraper.sources._filter import is_acceptable


def test_first_edition_is_rejected():
    assert is_acceptable("Pokemon Base Set 1st Edition Booster Box Sealed", 300_000) is False


def test_shadowless_is_rejected():
    assert is_acceptable("Pokemon Base Set Shadowless Booster Box Sealed", 90_000) is False


def test_unlimited_in_band_is_accepted():
    assert is_acceptable("Pokemon Base Set Unlimited Booster Box Sealed", 40_000) is True


def test_unlimited_parenthetical_is_accepted():
    assert is_acceptable("Pokemon Base Set Booster Box Sealed (Unlimited)", 35_000) is True


def test_no_edition_in_band_is_accepted():
    # No edition keyword and price is plausible — accept (best-effort).
    assert is_acceptable("Pokemon Base Set Booster Box", 40_000) is True


def test_no_edition_above_band_is_rejected():
    # Price suggests a 1st Edition mislabelled as plain "Base Set".
    assert is_acceptable("Pokemon Base Set Booster Box", 200_000) is False


def test_wrong_set_is_rejected():
    assert is_acceptable("Pokemon Jungle Booster Box Sealed", 4_000) is False


def test_no_shadow_variant_is_rejected():
    assert is_acceptable("Pokemon Base Set No-Shadow Booster Box Sealed", 90_000) is False


def test_first_edition_long_form_is_rejected():
    assert is_acceptable("Pokemon Base Set First Edition Booster Box Sealed", 300_000) is False


def test_below_band_is_rejected():
    # Way too cheap — probably a single pack or empty box.
    assert is_acceptable("Pokemon Base Set Booster Box Sealed", 200) is False


def test_none_title_is_rejected():
    assert is_acceptable(None, 40_000) is False

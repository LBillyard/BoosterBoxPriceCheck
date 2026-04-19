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


# --- New exclusions covering modern reprints + foreign-language vintage. ---

def test_base_set_2_is_rejected():
    # Base Set 2 is a 2000 reprint, separate SKU. Sometimes priced in-band
    # for collectors, but it is not the product the user is tracking.
    assert is_acceptable(
        "Pokemon Cards Base Set 2 Booster Box Sealed 36 packs WOTC vintage",
        15_004,
    ) is False


def test_mega_evolution_base_set_is_rejected():
    # Mega Evolution "Base Set" is modern Pokemon TCG — wrong product.
    assert is_acceptable(
        "Pokemon TCG Mega Evolution Base Set Booster Box SEALED ME01",
        20_000,
    ) is False


def test_scarlet_violet_base_set_is_rejected():
    assert is_acceptable(
        "Pokemon Scarlet and Violet Base Set Booster Box Sealed",
        20_000,
    ) is False


def test_foreign_language_base_set_is_rejected():
    # User tracks the English Unlimited print specifically.
    assert is_acceptable(
        "Factory Sealed Pokemon Base Set Unlimited Booster Box Spanish",
        16_000,
    ) is False
    assert is_acceptable(
        "Pokemon TCG Base Set 1st Edition Booster Box German 1999",
        16_000,
    ) is False


def test_empty_box_is_rejected():
    assert is_acceptable(
        "Pokemon TCG 1999 Base Set Unlimited *EMPTY* Booster Box English",
        16_000,
    ) is False


def test_real_unlimited_with_acrylic_is_accepted():
    # Real example from eBay US sold listings: must still pass.
    assert is_acceptable(
        "Pokemon EN Base Set Unlimited Booster Box WOTC Factory Sealed w/ Acrylic Case",
        36_600,
    ) is True


def test_green_wings_unlimited_is_accepted():
    # "GREEN WINGS" is collector shorthand for the Unlimited variant.
    assert is_acceptable(
        "Original WOTC Base Set SEALED Booster Box GREEN WINGS (Pokemon Cards)",
        42_500,
    ) is True

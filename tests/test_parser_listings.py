from pathlib import Path
from scraper.parser import parse_listings

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_listings_returns_list_of_dicts():
    html = FIXTURE.read_text(encoding="utf-8")
    listings = parse_listings(html)
    # Booster boxes are not always listed; allow empty but type must be list.
    assert isinstance(listings, list)
    for item in listings:
        assert "usd_cents" in item
        assert isinstance(item["usd_cents"], int)
        assert "condition" in item

from pathlib import Path
from scraper.parser import parse_prices

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_prices_returns_known_conditions():
    html = FIXTURE.read_text(encoding="utf-8")
    prices = parse_prices(html)
    # PriceCharting always shows at least these for sealed product:
    assert "loose" in prices or "new" in prices or "sealed" in prices
    # Every value should be an int number of cents (matches API convention)
    for cond, cents in prices.items():
        assert isinstance(cents, int), f"{cond} should be int cents"
        assert cents > 100_000, f"{cond}={cents} suspiciously low for a Base Set box"

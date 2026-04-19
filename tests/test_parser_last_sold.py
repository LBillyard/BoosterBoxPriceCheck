from pathlib import Path
from scraper.parser import parse_last_sold

FIXTURE = Path(__file__).parent / "fixtures" / "booster_box.html"

def test_parse_last_sold_returns_price_and_date():
    html = FIXTURE.read_text(encoding="utf-8")
    result = parse_last_sold(html)
    assert result is not None
    assert isinstance(result["usd_cents"], int)
    assert result["usd_cents"] > 100_000
    assert result["date"]  # ISO date string

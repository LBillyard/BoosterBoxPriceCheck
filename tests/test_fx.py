from unittest.mock import patch
from scraper.fx import fetch_usd_to_gbp

def test_fetch_usd_to_gbp_parses_response():
    fake = {"amount": 1.0, "base": "USD", "date": "2026-04-19", "rates": {"GBP": 0.7945}}
    with patch("scraper.fx.requests.get") as m:
        m.return_value.json.return_value = fake
        m.return_value.raise_for_status.return_value = None
        rate = fetch_usd_to_gbp()
    assert rate == 0.7945

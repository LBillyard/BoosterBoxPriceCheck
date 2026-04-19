import requests

FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=GBP"

def fetch_usd_to_gbp(timeout: int = 10) -> float:
    r = requests.get(FRANKFURTER_URL, timeout=timeout)
    r.raise_for_status()
    return float(r.json()["rates"]["GBP"])

# BoosterBoxPriceCheck

Always-on price display for a Pokémon Base Set Booster Box.

🔗 **Live page:** https://lbillyard.github.io/BoosterBoxPriceCheck/

A GitHub Actions cron scrapes [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/booster-box) every 12 hours, fetches USD→GBP from [frankfurter.app](https://www.frankfurter.app/), and commits the snapshot. The static site fetches the snapshot and renders a clean white display. Installable as a PWA on Android (Add to Home screen) for a permanent always-on phone display.

## Layout

- `scraper/` — Python scraper (parser, FX, orchestrator)
- `tests/` — pytest tests with HTML fixture
- `web/` — static frontend (HTML, JS, CSS, PWA manifest, service worker)
- `data/` — committed snapshots from the cron
- `.github/workflows/` — `scrape.yml` (12-hourly cron) + `pages.yml` (deploy)
- `docs/plans/` — design + implementation plan

## Running locally

```bash
pip install -r scraper/requirements.txt
python -m scraper.scrape           # writes data/snapshot.json
mkdir -p web/data && cp data/snapshot.json web/data/
python -m http.server -d web 8000  # http://localhost:8000
```

## Tests

```bash
python -m pytest -v
```

# BoosterBoxPriceCheck

Always-on price display for a single high-value collectible (Pokémon Base Set Booster Box).

A GitHub Actions cron scrapes [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/booster-box) every 12 hours, fetches the current USD→GBP rate, and commits the snapshot back to this repo. A static page on GitHub Pages reads the snapshot and renders a clean white display showing current value, last sale, and active marketplace listings — designed to live full-screen on a cheap Android phone via PWA install.

## Status

🚧 In design. See [docs/plans/2026-04-19-booster-box-price-display-design.md](docs/plans/2026-04-19-booster-box-price-display-design.md).

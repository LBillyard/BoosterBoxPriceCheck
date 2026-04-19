# Booster Box Price Display — Design

**Date:** 2026-04-19
**Owner:** LBillyard
**Tracked item:** [Pokémon Base Set Booster Box on PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/booster-box) — purchase price £29,253.05

## Goal

A small always-on display showing the current market value, last sale, and active marketplace listings for a Pokémon Base Set Booster Box. Prices shown in both USD (source) and GBP (converted).

## User context

A cheap second-hand Android phone, plugged into permanent power, sat near the booster box display case. The phone runs the app full-screen via PWA install. The same view is also accessible from a desktop browser.

## Architecture

```
┌────────────────────────────┐    every 12h    ┌──────────────────────────┐
│   GitHub Actions cron      │  ─────────────▶ │  pricecharting.com       │
│   (scrape + FX fetch)      │                 │  frankfurter.app (FX)    │
└────────────┬───────────────┘                 └──────────────────────────┘
             │ commits data.json
             ▼
┌────────────────────────────┐    fetch on load   ┌────────────────────────┐
│   GitHub Pages (static)    │  ◀──────────────── │  Browser / PWA         │
│   index.html, JS, CSS      │                    │  (PC + Android phone)  │
└────────────────────────────┘                    └────────────────────────┘
```

No always-on server. The repo itself is the database — every scrape is a commit, giving free price history.

## Components

### 1. Scraper (Python, runs in GitHub Actions)
- Fetches the PriceCharting page with a realistic browser User-Agent.
- Parses: current prices per condition (loose / CIB / new / sealed), last-sold price + date, active marketplace listings (condition, price, seller).
- Fetches USD→GBP rate from `frankfurter.app` (free, no API key).
- Writes `data/snapshot.json` and commits with message `chore: snapshot YYYY-MM-DD HH:MM`.
- On parse failure: writes a `data/error.json` with the failure reason and timestamp; the previous good `snapshot.json` stays in place.

### 2. Frontend (static HTML/CSS/JS, served by GitHub Pages)
- Single `index.html`, vanilla JS, no build step.
- On load: fetches `data/snapshot.json` from the repo (raw GitHub URL or relative path).
- Renders the layout (see below).
- Re-fetches every 5 minutes (cheap — the file barely changes).
- Shows a yellow "stale data" badge if `snapshot.json` is older than 24h or if `error.json` is newer.
- PWA manifest + service worker so Android can install it to the home screen and run full-screen.

### 3. Cron (GitHub Actions workflow)
- Schedule: `0 */12 * * *` (every 12 hours).
- Steps: checkout → run scraper → commit data files if changed → push.
- Manual `workflow_dispatch` trigger for on-demand runs.

## UI layout (mobile-first portrait)

```
┌──────────────────────────────────┐
│ Base Set Booster Box             │  ← title, light grey "updated 3h ago"
│                                  │
│         £28,940                  │  ← hero, big, accent green
│         $36,420                  │  ← secondary, smaller, grey
│                                  │
│  CIB    New    Sealed            │  ← condition row, 3 small cards
│  £18k   £29k   £40k              │
│                                  │
│  Last sold                       │
│  £28,400 · 2 days ago            │
│                                  │
│  12 listed · from £27,500        │  ← summary line
│  ─────────────────────────────   │
│  Sealed   £27,500   seller_a     │  ← scrollable list
│  Sealed   £28,000   seller_b     │
│  CIB      £18,200   seller_c     │
│  ...                             │
│                                  │
│            [ Refresh ]           │  ← manual refresh
└──────────────────────────────────┘
```

### Styling
- White background, dark text (#1a1a1a).
- Single accent colour for the hero price: muted green (#2f7a4d).
- Generous spacing, large readable numbers, system font stack.
- No shadows, no gradients, no emoji. Quiet and Apple-like.

## Data flow

1. Cron fires every 12 h.
2. Scraper hits PriceCharting → parses → hits frankfurter → writes `data/snapshot.json`:

```json
{
  "scraped_at": "2026-04-19T12:00:00Z",
  "fx": { "usd_to_gbp": 0.7945, "fetched_at": "2026-04-19T12:00:00Z" },
  "prices": {
    "loose":  { "usd": 36420, "gbp": 28940 },
    "cib":    { "usd": 22800, "gbp": 18114 },
    "new":    { "usd": 36800, "gbp": 29242 },
    "sealed": { "usd": 50300, "gbp": 39963 }
  },
  "last_sold": { "usd": 35750, "gbp": 28401, "date": "2026-04-17" },
  "listings": [
    { "condition": "Sealed", "usd": 34600, "gbp": 27499, "seller": "seller_a", "url": "..." },
    { "condition": "Sealed", "usd": 35200, "gbp": 27975, "seller": "seller_b", "url": "..." }
  ],
  "purchase_price_gbp": 29253.05
}
```

3. Frontend fetches `snapshot.json`, renders.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| PriceCharting blocks GitHub Actions IPs (403) | Use realistic User-Agent + headers. Fallback: switch scraper to Playwright headless. Last-resort: move scraper to a residential machine via cron + push. |
| PriceCharting changes HTML | Scraper logs parse error to `error.json`. UI shows "stale data" badge. Selectors live in one file for easy fixes. |
| FX API down | Reuse last-known FX rate from prior snapshot. |
| Phone screen burn-in | PWA can dim after N minutes of no interaction (out of scope v1, note for later). |

## Out of scope (for v1)

- Price history chart (data is being captured via commits — easy to add later).
- Notifications (e.g. price drop alerts).
- Multiple tracked items.
- Native `.apk` build (PWA is sufficient).
- Authentication (repo is public anyway).

## Tech choices

- **Scraper:** Python 3.11+, `requests` + `beautifulsoup4`. Add `playwright` only if HTTP scraping is blocked.
- **Frontend:** Plain HTML/CSS/JS. No framework, no build step.
- **CI:** GitHub Actions, single workflow file.
- **Hosting:** GitHub Pages from the same repo (`/` or `/docs`).

## Repo layout

```
BoosterBoxPriceCheck/
├── .github/workflows/scrape.yml
├── scraper/
│   ├── scrape.py
│   ├── selectors.py
│   └── requirements.txt
├── data/
│   ├── snapshot.json        ← committed by cron
│   └── error.json           ← only if last scrape failed
├── web/                     ← GitHub Pages root
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── sw.js
├── docs/plans/
│   └── 2026-04-19-booster-box-price-display-design.md
└── README.md
```

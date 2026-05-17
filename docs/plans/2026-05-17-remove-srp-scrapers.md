# Remove SRP Scrapers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Delete the patchright SRP scrapers, their shared transport, tests, fixtures, the patchright dependency, and the CI step that installs Chromium. Simplify `scraper/scrape.py` to its API-only shape.

**Architecture:** Pure deletion plus light orchestrator simplification — no new logic, no new tests. The live pipeline (PriceCharting parser + Browse API client + 2 marketplace sources) stays untouched.

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`, `pytest`. (Loses `patchright`.)

**Reference design:** [docs/plans/2026-05-17-remove-srp-scrapers-design.md](2026-05-17-remove-srp-scrapers-design.md)

---

## Task 1: Delete SRP source modules + their tests + their fixtures

**Files to delete (use `git rm`):**

- `scraper/sources/ebay_uk.py`
- `scraper/sources/ebay_us.py`
- `scraper/sources/ebay_us_active.py`
- `scraper/sources/ebay_uk_active.py`
- `scraper/sources/ebay_pinned.py`
- `scraper/sources/onethirtypoint.py`
- `scraper/sources/_browser.py`
- `scraper/sources/_ebay_item.py`
- `tests/test_source_ebay_uk.py`
- `tests/test_source_ebay_us.py`
- `tests/test_source_ebay_active.py`
- `tests/test_source_130point.py`
- `tests/fixtures/130point.html`
- `tests/fixtures/ebay_uk.html`
- `tests/fixtures/ebay_uk_synthetic.html`
- `tests/fixtures/ebay_us.html`

**Step 1: Sanity grep for cross-references**

Before deleting, grep the rest of the codebase for any imports of these modules. Run:

```bash
grep -rEn "from .*sources.*(ebay_uk|ebay_us|ebay_us_active|ebay_uk_active|ebay_pinned|onethirtypoint|_browser|_ebay_item)\b" scraper/ tests/ web/ docs/ || echo "no cross-references found"
```

Expected: matches only inside `scraper/scrape.py` (and inside the files we're deleting). If any other file imports them, stop and report — there's an unexpected dependency.

**Step 2: Run `git rm` on the entire delete list**

```bash
git rm scraper/sources/ebay_uk.py scraper/sources/ebay_us.py scraper/sources/ebay_us_active.py \
       scraper/sources/ebay_uk_active.py scraper/sources/ebay_pinned.py scraper/sources/onethirtypoint.py \
       scraper/sources/_browser.py scraper/sources/_ebay_item.py \
       tests/test_source_ebay_uk.py tests/test_source_ebay_us.py tests/test_source_ebay_active.py tests/test_source_130point.py \
       tests/fixtures/130point.html tests/fixtures/ebay_uk.html tests/fixtures/ebay_uk_synthetic.html tests/fixtures/ebay_us.html
```

**Step 3: Confirm working tree state**

Run `git status --short` — expect 16 lines, all `D ` (deleted, staged).

---

## Task 2: Simplify `scraper/scrape.py`

**Files:** Modify `scraper/scrape.py`.

**Step 1: Read the current file.**

**Step 2: Remove the now-broken imports**

The current import line is:

```python
from .sources import ebay_uk, ebay_us, ebay_us_active, ebay_api_us, ebay_api_uk
```

Replace with:

```python
from .sources import ebay_api_us, ebay_api_uk
```

**Step 3: Drop the SRP-related comment block at the top.**

The current file has a multi-paragraph comment explaining why `ebay_uk_active` and `ebay_pinned` are disabled (lines around 17-31). With the modules deleted, the comment is stale — remove the whole block. Replace with a single comment if helpful:

```python
# Live sources: PriceCharting (parser.py) + the official eBay Browse API
# (sources.ebay_api_us, sources.ebay_api_uk). The patchright SRP scrapers
# were removed on 2026-05-17 — see git log and docs/plans/.
```

**Step 4: Remove the SRP fetch loop in the recent-sales section**

Current code around line 149-155 reads:

```python
for name, fn in (
    ("ebay_uk",  lambda: ebay_uk.fetch(gbp_per_usd=fx)),
    ("ebay_us",  lambda: ebay_us.fetch()),
):
    rows = _run_with_timeout(name, fn)
    source_counts[name] = len(rows)
    recent_sales.extend(rows)
```

Delete this entire loop. The recent-sales block still keeps the PriceCharting "last sold" injection that follows.

**Step 5: Remove the ebay_us_active block in the active-listings section**

Current code around line 183-191 reads:

```python
rows = _run_with_timeout("ebay_us_active", lambda: ebay_us_active.fetch())
if not rows:
    print("INFO: ebay_us_active returned 0; retrying once", file=sys.stderr, flush=True)
    rows = _run_with_timeout("ebay_us_active(retry)", lambda: ebay_us_active.fetch())
source_counts["ebay_us_active"] = len(rows)
active_rows.extend(rows)
```

Delete the entire block.

**Step 6: Remove the `# ebay_pinned removed — see import-line comment for why.` line**

Replace with: nothing (just delete).

**Step 7: Confirm `_run_with_timeout` is still needed**

Yes — the two API sources still use it (90 s is generous for ~3 s calls, but the wrapper protects against network hangs). Keep `SOURCE_TIMEOUT_S = 90` and `_run_with_timeout` as-is.

**Step 8: Confirm the `os._exit(rc)` at the end is still needed**

The original reason was that abandoned patchright worker threads would block sys.exit. With patchright gone, this concern is moot — `requests` worker threads don't leak. Replace `os._exit(rc)` at the bottom with `sys.exit(rc)`, and update the surrounding comment:

```python
if __name__ == "__main__":
    sys.exit(main())
```

(Drop the long atexit-leaked-thread comment; it described a patchright-specific problem we no longer have.)

**Step 9: Save and run the full test suite**

```bash
python -m pytest -v
```

Expect: all remaining tests pass. The test count drops from 67 to ~28-30 (we removed ~37 SRP-related tests). Specifically:

- `test_filter.py` (~11 tests, kept)
- `test_fx.py` (~3 tests, kept)
- `test_history.py` (~3 tests, kept)
- `test_parser_*.py` (~7 tests, kept — PriceCharting parser)
- `test_snapshot.py` (~4 tests, kept)
- `test_source_ebay_api.py` (14 tests, kept)

If anything else fails, stop and investigate before continuing.

---

## Task 3: Drop patchright from requirements

**Files:** Modify `scraper/requirements.txt`.

**Step 1:** Remove the line `patchright==1.58.2`.

**Step 2:** Run `pip install -r scraper/requirements.txt` to confirm the file is still valid. Expected: all 4 remaining deps satisfied.

(Optional cleanup: `pip uninstall patchright` locally. Not required — pip won't auto-remove unused packages.)

---

## Task 4: Drop the patchright Chromium install step from CI

**Files:** Modify `.github/workflows/scrape.yml`.

**Step 1:** Read the workflow.

**Step 2:** Remove the step that installs the patchright Chromium binary. Typically named something like "Install patchright Chromium" with `run: patchright install chromium` or similar.

**Step 3:** Run `python -c "import yaml; yaml.safe_load(open('.github/workflows/scrape.yml'))"` — silent success.

---

## Task 5: Update `tests/fixtures/README.md`

**Files:** Modify `tests/fixtures/README.md`.

The current README has a paragraph about HTML fixtures used by the SRP-scraper tests. With the HTML fixtures and their tests gone, that paragraph is dead. Replace it with a single line noting `booster_box.html` is the PriceCharting parser fixture.

---

## Task 6: Local end-to-end verification

**Step 1:** Run `python -m scraper.scrape` (with `.env` populated for live API calls).

Expected output:

- Exit 0.
- No mention of `ebay_uk`, `ebay_us`, `ebay_us_active` in logs (those sources no longer exist).
- `INFO: source ebay_api_us returned N rows in <3s` and `INFO: source ebay_api_uk returned M rows`.
- `data/snapshot.json` updated. `source_counts` now contains only `ebay_api_us`, `ebay_api_uk`, `pricecharting_last_sold`.
- Total runtime ~5-10 s (vs ~3 min before).

**Step 2:** Compare snapshot to the previous one — `active_listings` should be the union of the two API sources, with no SRP-tagged rows.

---

## Task 7: Commit and push

**Step 1:** Stage everything:

```bash
git add -A
```

**Step 2:** Single squash-able commit:

```bash
git commit -m "$(cat <<'EOF'
refactor: remove patchright SRP scrapers; live pipeline is API + PriceCharting

The patchright-driven eBay UK/US SRP scrapers (sold + active) and the
130point Cloudflare-shielded fetcher have consistently returned 0 rows
from GitHub Actions IPs since eBay's bot detection refuses datacenter
traffic. The official Browse API source landed in #1 covers the same
data domain (active listings, US + UK) reliably and runs in ~3 seconds
instead of ~3 minutes per cron.

Deletes the source modules, their shared transport (_browser.py), the
ebay_us_active item-page helper, all SRP-specific tests and HTML
fixtures, the patchright Python dependency, and the CI step that
downloads patchright's bundled Chromium. Simplifies the orchestrator
in scraper/scrape.py to its API-only shape and reverts the
patchright-specific os._exit() hack back to a normal sys.exit().

PriceCharting parsing (parser.py + booster_box.html fixture), the FX
fetcher, the snapshot builder, and the shared _filter.is_acceptable
all stay — none touched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Step 3:** Push and open PR:

```bash
git push -u origin feat/remove-srp-scrapers
gh pr create --title "refactor: remove patchright SRP scrapers" --body "$(cat <<'EOF'
## Summary
- Removes the patchright SRP scrapers (eBay UK/US sold + active, 130point) and their shared transport — they've been returning 0 rows from GitHub Actions IPs since bot detection started refusing datacenter traffic.
- Drops the patchright Python dependency and the CI Chromium install step. Cron runtime drops ~3 min → ~30 s.
- Browse API source (#1) is the sole eBay path; PriceCharting parser is unchanged and still feeds the headline numbers.

## Test plan
- [x] Full test suite passes (count drops from 67 to ~28 after removing the SRP test files)
- [x] Local end-to-end scrape produces a valid snapshot with `source_counts.ebay_api_us > 0` (or 0 if no live listings match) and no SRP keys
- [ ] CI run on this branch produces the same shape as #1's verification run

## Reference
- Design: [docs/plans/2026-05-17-remove-srp-scrapers-design.md](docs/plans/2026-05-17-remove-srp-scrapers-design.md)
- Plan: [docs/plans/2026-05-17-remove-srp-scrapers.md](docs/plans/2026-05-17-remove-srp-scrapers.md)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Capture the PR URL.

---

## Notes for the executing agent

- This is pure deletion + light orchestrator edits. No new code, no new tests, no TDD discipline needed.
- Skill-check at the start of each task: `superpowers:verification-before-completion` before any commit that claims a task is done. After Task 2, run pytest. After Task 6, run the end-to-end scraper.
- If a grep in Task 1 Step 1 surfaces an unexpected import, STOP — there's a coupling I haven't accounted for. Report back before deleting anything.

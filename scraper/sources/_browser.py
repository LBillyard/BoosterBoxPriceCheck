"""Shared headless-browser fetcher for sources that need JS rendering.

Several sources (130point.com behind Cloudflare; eBay's modern SRP) refuse to
serve usable HTML to a plain ``requests`` client. ``render(url, ...)`` drives
a real Chromium via Playwright, returning the post-render HTML string. This
module deliberately does *no* parsing — each source still owns its own
BeautifulSoup logic; this is just the transport.

Why a shared helper:
    * Both 130point and eBay UK now need the same browser shape (real UA,
      en-GB locale, desktop viewport, suppressed automation flag). Putting
      one copy here means a fingerprint tweak fixes every source at once.
    * Playwright launches are not free (~1s spin-up). Sources call this
      lazily, once per fetch, so the cost only lands when the orchestrator
      decides to refresh sales.

Failure mode: if Playwright is not installed (e.g. dev environment without
``pip install playwright`` + ``playwright install chromium``) ``render()``
raises ``ImportError``. Sources are wrapped in try/except inside the
orchestrator, so an absent browser degrades to "this source returns 0 rows"
rather than crashing the whole snapshot.
"""
from __future__ import annotations


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch_html(url: str, locale: str = "en-GB", timeout: int = 25) -> str:
    """Plain-HTTP GET with realistic Chrome headers — for sites that
    don't bot-block (eBay).

    Single request, no retry. Caller's parser returns [] if the page is
    a JS-shell. Two orders of magnitude faster than Chromium per scrape.
    """
    import requests
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{locale},en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def render(
    url: str,
    wait_selector: str | None = None,
    timeout_ms: int = 30000,
    selector_timeout_ms: int = 10000,
    locale: str = "en-GB",
) -> str:
    """Fetch ``url`` through headless Chromium and return rendered HTML.

    Parameters
    ----------
    url:
        Target URL.
    wait_selector:
        Optional CSS selector to wait for after ``domcontentloaded``. Useful
        when the interesting markup is injected by a second-stage XHR (eBay
        SRP cards) or revealed only after a Cloudflare challenge resolves
        (130point). If the selector never appears we fall through with
        whatever HTML loaded — the caller's parser will return an empty
        list, which is the correct degradation.
    timeout_ms:
        Hard ceiling for the initial navigation.
    selector_timeout_ms:
        How long to wait for ``wait_selector`` (if provided).
    locale:
        Browser locale. Defaults to ``en-GB`` so that eBay UK formats
        prices in £ and dates as "16 Apr 2026" — matching the parser.
    """
    # Imported lazily so the rest of the package still imports in
    # environments without Playwright (e.g. lint, unit tests over fixtures).
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        try:
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                locale=locale,
                viewport={"width": 1280, "height": 900},
                # Pretend we don't speak the headless protocol so sites
                # that probe ``navigator.webdriver`` see ``undefined``.
                java_script_enabled=True,
            )
            # Patch ``navigator.webdriver`` before the page script runs.
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined});"
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(
                        wait_selector, timeout=selector_timeout_ms
                    )
                except Exception:
                    # Soft fail — caller's parser handles empty/malformed
                    # markup by returning [].
                    pass
            return page.content()
        finally:
            browser.close()

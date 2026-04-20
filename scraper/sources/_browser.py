"""Shared headless-browser fetcher for sources that need JS rendering.

Several sources (130point.com behind Cloudflare; eBay US's modern SRP when
served from a datacenter IP) refuse to serve usable HTML to a plain
``requests`` client. ``render(url, ...)`` drives a real Chromium via
**patchright** — a stealth-patched fork of Playwright that hides the usual
automation fingerprints (CDP runtime ID, ``navigator.webdriver``, headless
shell quirks) — and returns the post-render HTML string. This module
deliberately does *no* parsing; each source still owns its own
BeautifulSoup logic, this is just the transport.

Why patchright instead of vanilla Playwright:
    * Vanilla Playwright loses to Cloudflare Turnstile (130point) and to
      eBay's bot-protection on US datacenter IPs (the GitHub Actions
      runners). patchright's API is a drop-in replacement —
      ``from patchright.sync_api import sync_playwright`` — but the
      bundled Chromium build patches the CDP fingerprint that triggers
      those challenges.

Why a shared helper:
    * Every JS-needing source benefits from the same browser shape (real
      UA via Chromium's default, locale, desktop viewport). One module
      means a fingerprint tweak fixes every source at once.
    * Browser launches are not free (~1-2s spin-up). Sources call this
      lazily, once per fetch, so the cost only lands when the
      orchestrator decides to refresh sales.

Failure mode: if patchright is not installed (e.g. dev environment without
``pip install patchright`` + ``patchright install chromium``) ``render()``
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
    # environments without patchright (e.g. lint, unit tests over fixtures).
    # patchright is a stealth-patched, drop-in API replacement for
    # ``playwright.sync_api`` — same context manager, same browser/page
    # objects, but the bundled Chromium hides the CDP fingerprint that
    # Cloudflare Turnstile and eBay's bot detector key on.
    from patchright.sync_api import sync_playwright

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
            # Clamp every page operation (waitForXxx, click, etc.) to a
            # hard ceiling. Without this, a Cloudflare challenge that
            # never resolves can leave the page indefinitely loading.
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
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


def render_many(
    urls: list[str],
    wait_selector: str | None = None,
    timeout_ms: int = 30000,
    selector_timeout_ms: int = 8000,
    locale: str = "en-GB",
) -> dict[str, str]:
    """Fetch multiple URLs in a SINGLE patchright browser session.

    Reusing the browser context across navigations means we pay the
    ~5-15s Chromium spin-up cost once instead of N times. Cookies and
    fingerprint persist across hops, which also makes us look more
    human to bot detectors that key on session continuity.

    Returns ``{url: html}``. URLs that fail to load (timeout, network
    error) get an empty string so callers can detect the failure
    without raising.
    """
    from patchright.sync_api import sync_playwright

    out: dict[str, str] = {}
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
                java_script_enabled=True,
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined});"
            )
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if wait_selector:
                        try:
                            page.wait_for_selector(
                                wait_selector, timeout=selector_timeout_ms
                            )
                        except Exception:
                            pass
                    out[url] = page.content()
                except Exception:
                    out[url] = ""
            return out
        finally:
            browser.close()

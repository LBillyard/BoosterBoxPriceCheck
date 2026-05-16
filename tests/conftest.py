"""Pytest fixtures shared across the test suite."""
import pytest


@pytest.fixture(autouse=True)
def _reset_ebay_api_token_cache():
    """Clear the in-process eBay OAuth token cache before AND after every test.

    The cache is a module-global in :mod:`scraper.sources._ebay_api_client`.
    Without resetting between tests, mocks added in later test files (e.g.
    monkeypatched ``_get_token``) can leak a stale value into neighbouring
    tests via the cache. Resetting at both ends keeps tests order-independent.
    """
    from scraper.sources import _ebay_api_client
    _ebay_api_client._cached_token = None
    yield
    _ebay_api_client._cached_token = None

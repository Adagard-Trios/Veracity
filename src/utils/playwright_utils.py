"""
Playwright Utility — Synchronous headless-browser fallback scraper.

Used when no API exists for a page or when JavaScript-heavy sites
(LinkedIn Ad Library, BigSpy, Google Ads Transparency, dynamic SPAs)
cannot be scraped by Firecrawl alone.

Install:
  pip install playwright
  playwright install chromium       # one-time browser binary download

This module uses the synchronous Playwright API so it integrates
cleanly with LangGraph's synchronous node functions.

All scraping is done with Chromium in headless mode.  For sites that
require cookies / login flows, callers can pass `storage_state`.
"""

from __future__ import annotations

import re
import time
from typing import Any


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def playwright_scrape(
    url: str,
    wait_for_selector: str | None = None,
    scroll_count: int = 2,
    timeout_ms: int = 20_000,
    storage_state: str | dict | None = None,
    extract_selector: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str:
    """Scrape a URL using a headless Chromium browser (sync Playwright).

    Args:
        url:                Target URL to load.
        wait_for_selector:  Optional CSS selector to wait for before scraping.
                            E.g. ".ad-card", "#results". If None, waits for
                            "networkidle" instead.
        scroll_count:       How many times to scroll to the bottom to trigger
                            lazy-loading.  Each scroll waits 1.5 s for new
                            content to load.
        timeout_ms:         Page navigation timeout in milliseconds.
        storage_state:      Optional path to a Playwright storage-state JSON file
                            (for session cookies / auth).  Can also be a dict.
        extract_selector:   If set, only text inside matching elements is
                            returned. Useful for extracting specific regions
                            (e.g. ".feed-list-item", "[data-test='ad-unit']").
        extra_headers:      Optional HTTP headers to send with the request.

    Returns:
        Scraped page content as plain text / simplified markdown.
        Returns an error string prefixed with "(Playwright error: ...)" on failure.

    Raises:
        ImportError: If the playwright package is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        }

        browser = pw.chromium.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        }
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        if extra_headers:
            context_kwargs["extra_http_headers"] = extra_headers

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            # Wait for a specific element or network idle
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=10_000)
                except Exception:
                    pass  # Selector not found — proceed with current state
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass

            # Scroll to load lazy content
            for _ in range(scroll_count):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            # Extract text from a specific selector or the full page
            if extract_selector:
                elements = page.query_selector_all(extract_selector)
                texts = []
                for el in elements:
                    t = el.inner_text()
                    if t and t.strip():
                        texts.append(t.strip())
                raw_text = "\n\n---\n\n".join(texts)
            else:
                raw_text = page.inner_text("body")

            return _clean_text(raw_text)

        except Exception as exc:
            return f"(Playwright error: {exc})"
        finally:
            context.close()
            browser.close()


def playwright_screenshot(url: str, output_path: str, timeout_ms: int = 20_000) -> str:
    """Take a full-page screenshot — useful for visual ad verification.

    Args:
        url:         Target URL.
        output_path: File path to save the PNG screenshot.
        timeout_ms:  Navigation timeout.

    Returns:
        "OK: {output_path}" on success or error string on failure.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return "(Playwright error: not installed. Run: pip install playwright && playwright install chromium)"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            page.screenshot(path=output_path, full_page=True)
            return f"OK: {output_path}"
        except Exception as exc:
            return f"(Playwright screenshot error: {exc})"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Private: text cleanup
# ---------------------------------------------------------------------------
def _clean_text(text: str) -> str:
    """Normalise whitespace and remove common boilerplate noise."""
    if not text:
        return ""
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove zero-width and non-printable chars
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    # Normalise tabs
    text = text.replace("\t", "  ")
    return text.strip()

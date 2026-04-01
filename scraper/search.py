import asyncio
from playwright.async_api import BrowserContext

QOGITA_BASE = "https://www.qogita.com"
SEARCH_URL = "https://www.qogita.com/catalog?query={gtin}"

# Wait up to this long for the offer section to appear after navigation
OFFER_SECTION_TIMEOUT = 20000


async def get_product_page_html(gtin: str, context: BrowserContext, retries: int = 3) -> str | None:
    """
    Navigate to Qogita product page for a GTIN.
    Waits for the "Lowest priced offer" section to fully render before returning HTML.
    Returns the full page HTML, or None if not found.
    """
    page = None
    for attempt in range(retries):
        try:
            page = await context.new_page()
            url = SEARCH_URL.format(gtin=gtin)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Click first product result
            results_locator = page.locator("a[href*='/products/']")
            count = await results_locator.count()
            if count == 0:
                await page.close()
                page = None
                return None

            await results_locator.first.click()

            # Wait for JS to fully render the offer section before grabbing HTML.
            # This is the critical fix — domcontentloaded fires before React renders the prices.
            try:
                await page.wait_for_selector(
                    "text=Lowest priced offer",
                    timeout=OFFER_SECTION_TIMEOUT
                )
            except Exception:
                # Offer section never appeared — product may have no offers
                pass

            # Extra 2-second delay to be polite to Qogita's servers and avoid rate limiting
            await asyncio.sleep(2)

            html = await page.content()
            await page.close()
            page = None
            return html

        except Exception as e:
            if page is not None:
                await page.close()
                page = None
            if attempt == retries - 1:
                raise
            await asyncio.sleep(5)

    return None

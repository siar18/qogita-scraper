import asyncio
from playwright.async_api import BrowserContext

QOGITA_BASE = "https://www.qogita.com"
SEARCH_URL = "https://www.qogita.com/catalog?query={gtin}"


async def get_product_page_html(gtin: str, context: BrowserContext, retries: int = 3) -> str | None:
    """
    Navigate to Qogita product page for a GTIN.
    Returns the full page HTML, or None if not found.
    """
    for attempt in range(retries):
        try:
            page = await context.new_page()
            url = SEARCH_URL.format(gtin=gtin)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Click first product result
            first_result = page.locator("a[href*='/products/']").first
            count = await first_result.count()
            if count == 0:
                await page.close()
                return None

            await first_result.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            html = await page.content()
            await page.close()
            return html

        except Exception as e:
            await page.close()
            if attempt == retries - 1:
                raise
            await asyncio.sleep(5)

    return None

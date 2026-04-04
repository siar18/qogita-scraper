import asyncio
from playwright.async_api import BrowserContext

SEARCH_URL = "https://www.qogita.com/catalog?query={gtin}"
OFFER_SECTION_TIMEOUT = 25000

# Extract pricing data directly from Qogita's rendered DOM.
# Uses the grid layout Qogita uses: col-start-1 = unit prices, col-start-3 = stock.
_JS_EXTRACT = """
() => {
    // Product name
    const h1 = document.querySelector('h1');
    const productName = h1 ? h1.textContent.trim() : null;

    // Find the "Lowest priced offer" card — identified by shadow-custom2 class + h2 text
    let lowestCard = null;
    for (const card of document.querySelectorAll('[class*="shadow-custom2"]')) {
        for (const h2 of card.querySelectorAll('h2')) {
            if (h2.textContent.trim() === 'Lowest priced offer') {
                lowestCard = card;
                break;
            }
        }
        if (lowestCard) break;
    }

    if (!lowestCard) return null;

    // Supplier: <a> with font-outfit class containing all-caps alphanumeric code
    let supplier = null;
    for (const a of lowestCard.querySelectorAll('a[class*="font-outfit"]')) {
        const t = a.textContent.trim();
        if (/^[A-Z0-9]{4,8}$/.test(t)) { supplier = t; break; }
    }

    // Unit prices: spans with 'md:ml-auto' class (distinguishes unit price from MOV spans)
    const prices = [];
    for (const span of lowestCard.querySelectorAll('span[class*="md:ml-auto"]')) {
        const text = span.textContent.trim();
        const m = text.match(/€[\\s]*([\\d,.]+)/);
        if (m) {
            const p = parseFloat(m[1].replace(',', ''));
            if (!isNaN(p) && p > 0 && p < 100000) prices.push(p);
        }
    }
    if (prices.length === 0) return null;

    // Stock: <p> with col-start-4 class
    let stock = null;
    for (const p of lowestCard.querySelectorAll('p[class*="col-start-4"]')) {
        const t = p.textContent.trim();
        if (/^\\d+$/.test(t)) { stock = parseInt(t); break; }
    }

    return {
        product_name: productName,
        cheapest_seller: supplier,
        prices: prices,
        stock: stock
    };
}
"""


async def get_product_page_html(gtin: str, context: BrowserContext, retries: int = 3) -> tuple[str | None, dict | None]:
    """
    Navigate to Qogita product page for a GTIN.
    Returns (html, js_data):
      - js_data: structured data extracted from the live DOM (preferred, free)
      - html: raw page HTML kept as fallback for Claude extraction
      - (None, None): product not found on Qogita
    """
    page = None
    for attempt in range(retries):
        try:
            page = await context.new_page()
            url = SEARCH_URL.format(gtin=gtin)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the search dialog to render product results, then find the product URL
            # Product links have the form /products/{id}/{slug}/ (3+ segments)
            _PRODUCT_LINK_JS = r"""
                () => {
                    for (const a of document.querySelectorAll('a')) {
                        const href = a.getAttribute('href') || '';
                        if (/^\/products\/[^\/]+\/[^\/]+\//.test(href)) return href;
                    }
                    return null;
                }
            """
            try:
                await page.wait_for_function(_PRODUCT_LINK_JS, timeout=10000)
            except Exception:
                # No product found for this GTIN
                await page.close()
                page = None
                return None, None

            product_url = await page.evaluate(_PRODUCT_LINK_JS)
            if product_url is None:
                await page.close()
                page = None
                return None, None

            await page.goto(
                f"https://www.qogita.com{product_url}",
                wait_until="domcontentloaded",
                timeout=30000
            )

            # Wait for the "Lowest priced offer" section to fully render
            try:
                await page.wait_for_selector(
                    "text=Lowest priced offer",
                    timeout=OFFER_SECTION_TIMEOUT
                )
            except Exception:
                # Product exists but may have no offers
                pass

            # Small extra wait for all price tiers to render
            await asyncio.sleep(2)

            # Extract via JS from the live DOM
            js_data = await page.evaluate(_JS_EXTRACT)

            # Keep HTML only if JS failed (Claude fallback)
            html = None
            if js_data is None:
                html = await page.content()

            await page.close()
            page = None
            return html, js_data

        except Exception as e:
            if page is not None:
                await page.close()
                page = None
            if attempt == retries - 1:
                raise
            await asyncio.sleep(5)

    return None, None

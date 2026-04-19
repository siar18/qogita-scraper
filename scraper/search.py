import asyncio
from playwright.async_api import BrowserContext

SEARCH_URL = "https://www.qogita.com/catalog?query={gtin}"
OFFER_SECTION_TIMEOUT = 25000

# Extract ALL sellers from the page DOM.
# Each seller occupies a row div with both col-span-full and grid-flow-dense classes.
# Delivery: if an "Estimated delivery" button exists in the row, the seller is slow.
_JS_EXTRACT = """
() => {
    const h1 = document.querySelector('h1');
    const productName = h1 ? h1.textContent.trim() : null;

    function extractSeller(row) {
        // Supplier name — all-caps alphanumeric code in a font-outfit link
        let name = null;
        for (const a of row.querySelectorAll('a[class*="font-outfit"]')) {
            const t = a.textContent.trim();
            if (/^[A-Z0-9]{4,8}$/.test(t)) { name = t; break; }
        }
        if (!name) return null;

        // Unit price tiers — spans with md:ml-auto class
        const prices = [];
        for (const span of row.querySelectorAll('span[class*="md:ml-auto"]')) {
            const text = span.textContent.trim();
            const m = text.match(/\u20ac[\\s\\u00a0]*([\d,.]+)/);
            if (m) {
                const p = parseFloat(m[1].replace(',', ''));
                if (!isNaN(p) && p > 0 && p < 100000) prices.push(p);
            }
        }
        if (prices.length === 0) return null;

        // Stock — p with col-start-4 class
        let stock = null;
        for (const p of row.querySelectorAll('p[class*="col-start-4"]')) {
            const t = p.textContent.trim();
            if (/^\d+$/.test(t)) { stock = parseInt(t); break; }
        }

        // Delivery — any button containing "Estimated delivery" means slow delivery.
        // Capture the raw text for display; null means in-stock / immediate.
        let delivery = null;
        for (const btn of row.querySelectorAll('button')) {
            const t = btn.textContent.trim();
            if (t.toLowerCase().includes('estimated delivery')) {
                delivery = t.replace(/estimated delivery:?\\s*/i, '').trim();
                break;
            }
        }

        return { name, prices, stock, delivery };
    }

    const sellers = [];
    const seen = new Set();

    // Primary: each seller row is a div with both col-span-full and grid-flow-dense
    for (const row of document.querySelectorAll('div[class*="col-span-full"][class*="grid-flow-dense"]')) {
        const seller = extractSeller(row);
        if (seller && !seen.has(seller.name)) {
            seen.add(seller.name);
            sellers.push(seller);
        }
    }

    // Fallback: if primary found nothing, try the old lowest-card approach
    if (sellers.length === 0) {
        for (const card of document.querySelectorAll('[class*="shadow-custom2"]')) {
            for (const h2 of card.querySelectorAll('h2')) {
                if (h2.textContent.trim() === 'Lowest priced offer') {
                    const seller = extractSeller(card);
                    if (seller) sellers.push(seller);
                    break;
                }
            }
            if (sellers.length > 0) break;
        }
    }

    if (sellers.length === 0) return null;
    return { product_name: productName, sellers };
}
"""


async def get_product_page_html(gtin: str, context: BrowserContext, retries: int = 3) -> tuple[str | None, dict | None]:
    """
    Navigate to Qogita product page for a GTIN.
    Returns (html, js_data):
      - js_data: structured data with all sellers extracted from the live DOM (preferred, free)
      - html: raw page HTML kept as fallback for Claude extraction
      - (None, None): product not found on Qogita
    """
    page = None
    for attempt in range(retries):
        try:
            page = await context.new_page()
            url = SEARCH_URL.format(gtin=gtin)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

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

            try:
                await page.wait_for_selector(
                    "text=Lowest priced offer",
                    timeout=OFFER_SECTION_TIMEOUT
                )
            except Exception:
                pass

            await asyncio.sleep(2)

            js_data = await page.evaluate(_JS_EXTRACT)

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

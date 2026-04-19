import json
import re
from typing import Optional, TypedDict
import anthropic
from bs4 import BeautifulSoup


class Seller(TypedDict):
    name: str
    max_price: float
    stock: Optional[int]
    delivery: Optional[str]   # None = in stock / immediate; string = slow (e.g. "7 weeks")


class ProductData(TypedDict):
    product_name: Optional[str]
    sellers: list             # list of Seller dicts, sorted cheapest first
    extraction_method: str    # "js", "bs4", or "claude"
    # Convenience shortcuts from sellers[0] (kept for backward compat)
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]
    cheapest_seller_stock: Optional[int]


class ExtractionError(Exception):
    pass


def _parse_price(text: str) -> Optional[float]:
    match = re.search(r"[\d]+[.,][\d]+", text.replace(",", "."))
    if match:
        return float(match.group().replace(",", "."))
    return None


def _seller_from_raw(raw: dict) -> Optional[Seller]:
    """Convert a raw seller dict (from JS or Claude) to a Seller TypedDict."""
    prices = raw.get("prices") or []
    if not prices:
        return None
    return Seller(
        name=raw.get("name") or "",
        max_price=max(prices),
        stock=raw.get("stock"),
        delivery=raw.get("delivery") or None,
    )


def extract_from_js_data(js_data: dict) -> ProductData:
    """Build ProductData from the JS-extracted dict. Zero API cost."""
    raw_sellers = js_data.get("sellers") or []
    sellers: list[Seller] = []
    for raw in raw_sellers:
        s = _seller_from_raw(raw)
        if s:
            sellers.append(s)

    cheapest = sellers[0] if sellers else None
    return ProductData(
        product_name=js_data.get("product_name"),
        sellers=sellers,
        cheapest_seller=cheapest["name"] if cheapest else None,
        cheapest_seller_max_price=cheapest["max_price"] if cheapest else None,
        cheapest_seller_stock=cheapest["stock"] if cheapest else None,
        extraction_method="js",
    )


def _extract_with_bs4(html: str) -> Optional[ProductData]:
    """
    Try to extract product data using HTML parsing.
    Returns at most the cheapest seller (lowest-priced offer section).
    Returns None if the structure isn't recognisable.
    """
    soup = BeautifulSoup(html, "html.parser")

    product_name = None
    el = soup.find("h1")
    if el and el.get_text(strip=True):
        product_name = el.get_text(strip=True)

    lowest_section = None
    for el in soup.find_all(string=re.compile(r"Lowest priced offer", re.I)):
        lowest_section = el.find_parent()
        if lowest_section:
            for _ in range(8):
                prices_in_section = lowest_section.find_all(string=re.compile(r"€\s*[\d]+"))
                if prices_in_section:
                    break
                lowest_section = lowest_section.parent
            break

    if lowest_section is None:
        return None

    cheapest_seller_name = None
    for el in lowest_section.find_all(string=re.compile(r"^[A-Z0-9]{4,8}$")):
        cheapest_seller_name = el.strip()
        break

    price_tiers = []
    for el in lowest_section.find_all(string=re.compile(r"€\s*[\d]")):
        price = _parse_price(el)
        if price is not None:
            price_tiers.append(price)

    if not price_tiers:
        return None

    stock = None
    for el in lowest_section.find_all(string=re.compile(r"^\s*\d+\s*$")):
        try:
            val = int(el.strip())
            if val > 0:
                stock = val
                break
        except ValueError:
            continue

    # Check for delivery indicator in this section
    delivery = None
    for el in lowest_section.find_all(string=re.compile(r"estimated delivery", re.I)):
        delivery = el.strip().replace("Estimated delivery:", "").replace("Estimated delivery", "").strip()
        break

    seller = Seller(
        name=cheapest_seller_name or "",
        max_price=max(price_tiers),
        stock=stock,
        delivery=delivery if delivery else None,
    )

    return ProductData(
        product_name=product_name,
        sellers=[seller],
        cheapest_seller=seller["name"],
        cheapest_seller_max_price=seller["max_price"],
        cheapest_seller_stock=seller["stock"],
        extraction_method="bs4",
    )


def _extract_section_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(string=re.compile(r"Lowest priced offer", re.I)):
        section = el.find_parent()
        if section:
            for _ in range(8):
                if section.find_all(string=re.compile(r"€\s*[\d]+")):
                    break
                section = section.parent
            h1 = soup.find("h1")
            h1_html = str(h1) if h1 else ""
            return h1_html + str(section)
    return html[:6000]


EXTRACTION_PROMPT = """You are a data extraction assistant. Given HTML from a Qogita product page, extract:
1. The product name (from the h1 tag)
2. ALL sellers listed — from both "Lowest priced offer" AND "other offers" sections.
   For each seller extract:
   - name: the all-caps alphanumeric supplier code (e.g. "GE2E7")
   - prices: all unit price tiers as a list of floats (strip the € symbol)
   - stock: stock quantity as integer, or null if not shown as a number
   - delivery: the delivery time string if an "Estimated delivery" indicator is present (e.g. "7 weeks"), or null if in stock

Return ONLY valid JSON:
{"product_name": "string or null", "sellers": [{"name": "string", "prices": [float, ...], "stock": integer or null, "delivery": "string or null"}, ...]}

If no offers exist: {"product_name": null, "sellers": []}
Only return JSON, no explanation."""


def extract_product_data(html: str, client: anthropic.Anthropic = None) -> ProductData:
    result = _extract_with_bs4(html)
    if result is not None:
        return result

    if client is None:
        client = anthropic.Anthropic()

    section_html = _extract_section_html(html)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": f"{EXTRACTION_PROMPT}\n\nHTML:\n{section_html}"}]
    )

    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ExtractionError(f"Claude returned non-JSON response: {raw[:200]}")

    sellers: list[Seller] = []
    for raw_seller in data.get("sellers", []):
        s = _seller_from_raw(raw_seller)
        if s:
            sellers.append(s)

    cheapest = sellers[0] if sellers else None
    return ProductData(
        product_name=data.get("product_name"),
        sellers=sellers,
        cheapest_seller=cheapest["name"] if cheapest else None,
        cheapest_seller_max_price=cheapest["max_price"] if cheapest else None,
        cheapest_seller_stock=cheapest["stock"] if cheapest else None,
        extraction_method="claude",
    )

import json
import re
from typing import Optional, TypedDict
import anthropic
from bs4 import BeautifulSoup


class ProductData(TypedDict):
    product_name: Optional[str]
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]
    extraction_method: str  # "bs4" or "claude" — for diagnostics


class ExtractionError(Exception):
    pass


def _parse_price(text: str) -> Optional[float]:
    """Extract a float from a string like '€56.12' or '56,12'."""
    match = re.search(r"[\d]+[.,][\d]+", text.replace(",", "."))
    if match:
        return float(match.group().replace(",", "."))
    return None


def _extract_with_bs4(html: str) -> Optional[ProductData]:
    """
    Try to extract product data using HTML parsing.
    Returns None if the structure isn't recognisable — caller will fall back to Claude.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Product name — first h1 on the page
    product_name = None
    el = soup.find("h1")
    if el and el.get_text(strip=True):
        product_name = el.get_text(strip=True)

    # Find the "Lowest priced offer" section
    lowest_section = None
    for el in soup.find_all(string=re.compile(r"Lowest priced offer", re.I)):
        lowest_section = el.find_parent()
        if lowest_section:
            # Walk up until we find a container that also has prices
            for _ in range(8):
                prices_in_section = lowest_section.find_all(
                    string=re.compile(r"€\s*[\d]+")
                )
                if prices_in_section:
                    break
                lowest_section = lowest_section.parent
            break

    if lowest_section is None:
        return None

    # Supplier name — short all-caps alphanumeric codes like 2WYZL
    cheapest_seller = None
    for el in lowest_section.find_all(string=re.compile(r"^[A-Z0-9]{4,8}$")):
        cheapest_seller = el.strip()
        break

    # Price tiers — all euro amounts in the section
    price_tiers = []
    for el in lowest_section.find_all(string=re.compile(r"€\s*[\d]")):
        price = _parse_price(el)
        if price is not None:
            price_tiers.append(price)

    if not price_tiers:
        return None

    return ProductData(
        product_name=product_name,
        cheapest_seller=cheapest_seller,
        cheapest_seller_max_price=max(price_tiers),
        extraction_method="bs4",
    )


def _extract_section_html(html: str) -> str:
    """
    Return only the relevant offer-section HTML for Claude.
    Drastically reduces token usage vs sending the full page.
    Falls back to the first 6000 chars if section not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(string=re.compile(r"Lowest priced offer", re.I)):
        section = el.find_parent()
        if section:
            for _ in range(8):
                if section.find_all(string=re.compile(r"€\s*[\d]+")):
                    break
                section = section.parent
            # Also grab the h1 for the product name
            h1 = soup.find("h1")
            h1_html = str(h1) if h1 else ""
            return h1_html + str(section)
    return html[:6000]


EXTRACTION_PROMPT = """You are a data extraction assistant. Given HTML from a Qogita product page, extract:
1. The product name (from the h1 tag)
2. The name of the cheapest/lowest-priced supplier
3. All unit price tiers for that cheapest supplier, as a list of floats (strip the € symbol)

Return ONLY valid JSON:
{"product_name": "string or null", "cheapest_seller": "string or null", "price_tiers": [float, ...]}

If no offers exist: {"product_name": null, "cheapest_seller": null, "price_tiers": []}
Only return JSON, no explanation."""


def extract_product_data(html: str, client: anthropic.Anthropic = None) -> ProductData:
    # Try fast HTML parsing first — zero API cost
    result = _extract_with_bs4(html)
    if result is not None:
        return result

    # Fall back to Claude — send only the relevant section, not the full page
    if client is None:
        client = anthropic.Anthropic()

    section_html = _extract_section_html(html)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\nHTML:\n{section_html}"
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ExtractionError(f"Claude returned non-JSON response: {raw[:200]}")

    price_tiers: list[float] = data.get("price_tiers", [])

    return ProductData(
        product_name=data.get("product_name"),
        cheapest_seller=data.get("cheapest_seller"),
        cheapest_seller_max_price=max(price_tiers) if price_tiers else None,
        extraction_method="claude",
    )

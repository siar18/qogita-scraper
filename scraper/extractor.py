import json
import re
from typing import Optional, TypedDict
import anthropic
from bs4 import BeautifulSoup


class ProductData(TypedDict):
    product_name: Optional[str]
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]


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
    Returns None if the structure isn't recognisable.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Product name — first h1 or h2 on the page
    product_name = None
    for tag in ("h1", "h2"):
        el = soup.find(tag)
        if el and el.get_text(strip=True):
            product_name = el.get_text(strip=True)
            break

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

    # Supplier name — look for short all-caps alphanumeric codes (Qogita supplier IDs like 2WYZL)
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

    cheapest_seller_max_price = max(price_tiers)

    return ProductData(
        product_name=product_name,
        cheapest_seller=cheapest_seller,
        cheapest_seller_max_price=cheapest_seller_max_price,
    )


EXTRACTION_PROMPT = """You are a data extraction assistant. Given HTML from a Qogita product page, extract:
1. The product name (from the page heading)
2. The name of the cheapest/lowest-priced supplier (labeled "Lowest priced offer")
3. All unit price tiers for that cheapest supplier, as a list of floats

Return ONLY valid JSON in this exact format:
{
  "product_name": "string or null",
  "cheapest_seller": "string or null",
  "price_tiers": [float, float, ...]
}

If the product is not found or no offers exist, return:
{"product_name": null, "cheapest_seller": null, "price_tiers": []}

Do not include any explanation. Only return the JSON object."""


def extract_product_data(html: str, client: anthropic.Anthropic = None) -> ProductData:
    # Try fast HTML parsing first — no API cost
    result = _extract_with_bs4(html)
    if result is not None:
        return result

    # Fall back to Claude only when HTML parsing fails
    if client is None:
        client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\nHTML:\n{html[:8000]}"
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ExtractionError(f"Claude returned non-JSON response: {raw[:200]}")

    price_tiers: list[float] = data.get("price_tiers", [])
    cheapest_seller_max_price = max(price_tiers) if price_tiers else None

    return ProductData(
        product_name=data.get("product_name"),
        cheapest_seller=data.get("cheapest_seller"),
        cheapest_seller_max_price=cheapest_seller_max_price,
    )

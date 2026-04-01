import json
from typing import Optional, TypedDict
import anthropic


class ProductData(TypedDict):
    product_name: Optional[str]
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]


class ExtractionError(Exception):
    pass


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

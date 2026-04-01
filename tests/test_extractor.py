import pytest
from unittest.mock import MagicMock, patch
from scraper.extractor import extract_product_data, ProductData, ExtractionError


SAMPLE_HTML = """
<h1>Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml</h1>
<div>
  <p class="font-medium">Unit price</p>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€56.12</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€57.28</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€58.30</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€60.28</span>
  <p class="font-medium">Supplier: 2WYZL</p>
</div>
"""

MOCK_CLAUDE_RESPONSE = '{"product_name": "Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml", "cheapest_seller": "2WYZL", "price_tiers": [56.12, 57.28, 58.30, 60.28]}'


def test_extract_product_data_returns_product_data():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=MOCK_CLAUDE_RESPONSE)]
    )
    result = extract_product_data(SAMPLE_HTML, client=mock_client)
    assert result["product_name"] == "Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml"
    assert result["cheapest_seller"] == "2WYZL"
    assert result["cheapest_seller_max_price"] == 60.28


def test_extract_returns_none_when_not_found():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"product_name": null, "cheapest_seller": null, "price_tiers": []}')]
    )
    result = extract_product_data("<html>No product here</html>", client=mock_client)
    assert result["cheapest_seller"] is None
    assert result["cheapest_seller_max_price"] is None


def test_extract_raises_on_invalid_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Sorry I cannot help with that")]
    )
    with pytest.raises(ExtractionError):
        extract_product_data(SAMPLE_HTML, client=mock_client)

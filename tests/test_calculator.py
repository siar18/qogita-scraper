from scraper.calculator import calculate_row, PricingResult


def test_lower_needed():
    result = calculate_row(
        your_price=65.00,
        cost_price=45.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    assert result["suggested_price"] == round(60.28 / 1.12, 2)
    assert result["difference"] == round(result["suggested_price"] - 65.00, 2)
    assert result["notes"] == "Lower needed"


def test_already_competitive():
    result = calculate_row(
        your_price=50.00,
        cost_price=40.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    assert result["notes"] == "Already competitive"


def test_cant_compete():
    result = calculate_row(
        your_price=65.00,
        cost_price=55.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    # suggested = 60.28/1.12 = 53.82, which is below cost_price 55.00
    assert result["suggested_price"] == round(60.28 / 1.12, 2)
    assert result["notes"] == "Can't compete"


def test_not_found():
    result = calculate_row(
        your_price=65.00,
        cost_price=45.00,
        cheapest_max_price=None,
        margin_divisor=1.12
    )
    assert result["suggested_price"] is None
    assert result["difference"] is None
    assert result["notes"] == "Not found"

from typing import TypedDict, Optional


class PricingResult(TypedDict):
    suggested_price: Optional[float]
    difference: Optional[float]
    notes: str


def calculate_row(
    your_price: float,
    cost_price: float,
    cheapest_max_price: Optional[float],
    margin_divisor: float,
) -> PricingResult:
    if cheapest_max_price is None:
        return PricingResult(suggested_price=None, difference=None, notes="Not found")

    suggested_price = round(cheapest_max_price / margin_divisor, 2)

    if suggested_price < cost_price:
        return PricingResult(
            suggested_price=suggested_price,
            difference=round(suggested_price - your_price, 2),
            notes="Can't compete"
        )

    difference = round(suggested_price - your_price, 2)

    if difference > 0:
        # Your price is below the suggested price — you can raise it
        notes = "Price increase possible"
    elif difference == 0:
        notes = "Optimal price"
    else:
        notes = "Lower needed"

    return PricingResult(suggested_price=suggested_price, difference=difference, notes=notes)

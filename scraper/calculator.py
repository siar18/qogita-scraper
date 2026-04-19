from typing import Optional


def _profit(price: float, cost_price: float) -> tuple[Optional[float], Optional[float]]:
    """Return (profit_eur, profit_pct) or (None, None) if inputs are invalid."""
    if price is None or cost_price is None or cost_price <= 0:
        return None, None
    eur = round(price - cost_price, 2)
    pct = round(((price - cost_price) / cost_price) * 100, 1)
    return eur, pct


def _scenario_a_notes(suggested: float, your_price: float, cost_price: float) -> str:
    if suggested < cost_price:
        return "Can't compete"
    if your_price <= 0:
        return "No current price set"
    diff = round(suggested - your_price, 2)
    if diff > 0:
        return "Price increase possible"
    elif diff == 0:
        return "Optimal price"
    else:
        return "Lower needed"


def calculate_all_scenarios(
    your_price: float,
    cost_price: float,
    sellers: list,
    margin_divisor: float,
    min_stock: int = 6,
    low_stock_gap_threshold: float = 0.10,
) -> dict:
    """
    Calculate up to 3 pricing scenarios based on extracted seller data.

    sellers: list of Seller dicts sorted cheapest first.
             Each has: name, max_price, stock, delivery

    Returns dict with keys: current, scenario_a, scenario_b, scenario_c

    Scenario A — Be cheapest seller (always calculated)
        Suggested = seller_1_max / margin_divisor
        Will you be cheapest? Yes if suggested < seller_1_max (always true when divisor > 1)

    Scenario B — Long delivery (only when seller 1 has a delivery indicator)
        Seller 1 is slow → price as 2nd best using seller 2 as reference
        Suggested = seller_2_max / margin_divisor
        Notes include seller 1's delivery text

    Scenario C — Low stock wait-out (only when seller 1 stock < min_stock AND gap > threshold)
        Seller 1 will sell out → price just under seller 2 to maximise profit
        Suggested = seller_2_max * 0.98  (2% under seller 2, no margin divisor — maximise upside)
        When seller 1 sells out you become cheapest at a premium price
    """
    # Current performance
    cur_eur, cur_pct = _profit(your_price, cost_price) if your_price > 0 else (None, None)
    current = {"profit_eur": cur_eur, "profit_pct": cur_pct}

    empty_scenario = {
        "suggested_price": None,
        "profit_eur": None,
        "profit_pct": None,
        "will_be_cheapest": None,
        "notes": "Not found",
    }

    if not sellers:
        return {
            "current": current,
            "scenario_a": empty_scenario,
            "scenario_b": None,
            "scenario_c": None,
        }

    s1 = sellers[0]
    s2 = sellers[1] if len(sellers) > 1 else None

    # --- Scenario A: be cheapest ---
    a_suggested = round(s1["max_price"] / margin_divisor, 2)
    a_eur, a_pct = _profit(a_suggested, cost_price)
    scenario_a = {
        "suggested_price": a_suggested,
        "profit_eur": a_eur,
        "profit_pct": a_pct,
        "will_be_cheapest": a_suggested < s1["max_price"],
        "notes": _scenario_a_notes(a_suggested, your_price, cost_price),
    }

    # --- Scenario B: seller 1 has slow delivery ---
    scenario_b = None
    if s1.get("delivery") is not None:
        if s2 is not None:
            b_suggested = round(s2["max_price"] / margin_divisor, 2)
            b_eur, b_pct = _profit(b_suggested, cost_price)
            scenario_b = {
                "suggested_price": b_suggested if b_suggested >= cost_price else None,
                "profit_eur": b_eur if b_suggested >= cost_price else None,
                "profit_pct": b_pct if b_suggested >= cost_price else None,
                "delivery_info": s1["delivery"],
                "notes": (
                    f"Seller 1 delivery: {s1['delivery']} — priced as 2nd best seller"
                    if b_suggested >= cost_price
                    else f"Seller 1 delivery: {s1['delivery']} — 2nd seller too cheap to compete"
                ),
            }
        else:
            scenario_b = {
                "suggested_price": None,
                "profit_eur": None,
                "profit_pct": None,
                "delivery_info": s1["delivery"],
                "notes": f"Seller 1 delivery: {s1['delivery']} — no 2nd seller available",
            }

    # --- Scenario C: seller 1 low stock + big price gap ---
    scenario_c = None
    s1_stock = s1.get("stock")
    if s2 is not None and s1_stock is not None and s1_stock < min_stock:
        gap = (s2["max_price"] - s1["max_price"]) / s1["max_price"]
        if gap >= low_stock_gap_threshold:
            c_suggested = round(s2["max_price"] * 0.98, 2)
            c_eur, c_pct = _profit(c_suggested, cost_price)
            if c_suggested >= cost_price:
                scenario_c = {
                    "suggested_price": c_suggested,
                    "profit_eur": c_eur,
                    "profit_pct": c_pct,
                    "price_gap_pct": round(gap * 100, 1),
                    "notes": (
                        f"Seller 1 has {s1_stock} units — "
                        f"gap {round(gap * 100, 1)}% — wait them out, be 2nd best"
                    ),
                }

    return {
        "current": current,
        "scenario_a": scenario_a,
        "scenario_b": scenario_b,
        "scenario_c": scenario_c,
    }


# Kept for the single-product MCP tool (get_product_price)
def calculate_row(
    your_price: float,
    cost_price: float,
    cheapest_max_price: Optional[float],
    margin_divisor: float,
) -> dict:
    if cheapest_max_price is None:
        return {"suggested_price": None, "difference": None, "notes": "Not found"}

    suggested_price = round(cheapest_max_price / margin_divisor, 2)

    if suggested_price < cost_price:
        return {
            "suggested_price": suggested_price,
            "difference": round(suggested_price - your_price, 2),
            "notes": "Can't compete",
        }

    difference = round(suggested_price - your_price, 2)
    if difference > 0:
        notes = "Price increase possible"
    elif difference == 0:
        notes = "Optimal price"
    else:
        notes = "Lower needed"

    return {"suggested_price": suggested_price, "difference": difference, "notes": notes}

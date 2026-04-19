import asyncio
import json
import os
import random
import anthropic
from scraper.config_loader import load_config
from scraper.sheet import fetch_sheet_rows, read_excel_rows
from scraper.auth import get_authenticated_context
from scraper.search import get_product_page_html
from scraper.extractor import extract_product_data, extract_from_js_data, ExtractionError
from scraper.calculator import calculate_all_scenarios
from output.writer import write_excel, AnalysisRow

CHECKPOINT_PATH = "checkpoint.json"
CONCURRENCY = 5


def _load_checkpoint() -> tuple[list, set, int, int, int, int]:
    if not os.path.exists(CHECKPOINT_PATH):
        return [], set(), 0, 0, 0, 0
    with open(CHECKPOINT_PATH) as f:
        data = json.load(f)
    print(f"Resuming from checkpoint: {data['processed']} products already done")
    return (
        data["results"],
        set(data["processed_gtins"]),
        data["error_count"],
        data["js_hits"],
        data["bs4_hits"],
        data["claude_fallbacks"],
    )


def _save_checkpoint(state: dict):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump({
            "processed": len(state["results"]),
            "processed_gtins": list(state["processed_gtins"]),
            "results": state["results"],
            "error_count": state["error_count"],
            "js_hits": state["js_hits"],
            "bs4_hits": state["bs4_hits"],
            "claude_fallbacks": state["claude_fallbacks"],
        }, f)


def _build_row(
    gtin: str,
    your_price: float,
    cost_price: float,
    product_data: dict,
    scenarios: dict,
    margin_divisor: float = 1.0,
) -> AnalysisRow:
    """Assemble an AnalysisRow from extracted product data and calculated scenarios."""
    sellers = product_data.get("sellers") or []
    s1 = sellers[0] if len(sellers) > 0 else {}
    s2 = sellers[1] if len(sellers) > 1 else {}

    sa = scenarios.get("scenario_a") or {}
    sb = scenarios.get("scenario_b") or {}
    sc = scenarios.get("scenario_c") or {}
    cur = scenarios.get("current") or {}

    return AnalysisRow(
        # Product
        gtin=gtin,
        product_name=product_data.get("product_name"),
        cost_price=cost_price,
        your_qogita_price=your_price,
        current_profit_eur=cur.get("profit_eur"),
        current_profit_pct=cur.get("profit_pct"),
        # Seller data — prices divided by margin_divisor to show effective selling price
        seller1_name=s1.get("name"),
        seller1_max_price=round(s1["max_price"] / margin_divisor, 2) if s1.get("max_price") else None,
        seller1_stock=s1.get("stock"),
        seller1_delivery=s1.get("delivery"),
        seller2_name=s2.get("name"),
        seller2_max_price=round(s2["max_price"] / margin_divisor, 2) if s2.get("max_price") else None,
        seller2_stock=s2.get("stock"),
        # Scenario A
        a_suggested_price=sa.get("suggested_price"),
        a_profit_eur=sa.get("profit_eur"),
        a_profit_pct=sa.get("profit_pct"),
        a_will_be_cheapest=sa.get("will_be_cheapest"),
        a_notes=sa.get("notes") or "",
        # Scenario B
        b_suggested_price=sb.get("suggested_price"),
        b_profit_eur=sb.get("profit_eur"),
        b_profit_pct=sb.get("profit_pct"),
        b_delivery_info=sb.get("delivery_info"),
        b_notes=sb.get("notes") or "",
        # Scenario C
        c_suggested_price=sc.get("suggested_price"),
        c_profit_eur=sc.get("profit_eur"),
        c_profit_pct=sc.get("profit_pct"),
        c_price_gap_pct=sc.get("price_gap_pct"),
        c_notes=sc.get("notes") or "",
    )


def _empty_row(gtin: str, your_price: float, cost_price: float, notes: str) -> AnalysisRow:
    """Build an AnalysisRow for products that could not be found or had errors."""
    return AnalysisRow(
        gtin=gtin,
        product_name=None,
        cost_price=cost_price,
        your_qogita_price=your_price,
        current_profit_eur=None,
        current_profit_pct=None,
        seller1_name=None, seller1_max_price=None, seller1_stock=None, seller1_delivery=None,
        seller2_name=None, seller2_max_price=None, seller2_stock=None,
        a_suggested_price=None, a_profit_eur=None, a_profit_pct=None,
        a_will_be_cheapest=None, a_notes=notes,
        b_suggested_price=None, b_profit_eur=None, b_profit_pct=None,
        b_delivery_info=None, b_notes="",
        c_suggested_price=None, c_profit_eur=None, c_profit_pct=None,
        c_price_gap_pct=None, c_notes="",
    )


async def _process_row(
    semaphore: asyncio.Semaphore,
    lock: asyncio.Lock,
    sheet_row: dict,
    i: int,
    total: int,
    context,
    claude_client,
    config: dict,
    state: dict,
):
    gtin = sheet_row["gtin"]
    your_price = sheet_row["unit_price"]
    cost_price = sheet_row["cost_price"]

    min_stock = config.get("min_stock", 6)
    low_stock_gap_threshold = config.get("low_stock_gap_threshold", 0.10)
    margin_divisor = config["margin_divisor"]

    await asyncio.sleep(random.uniform(0, 2))
    async with semaphore:
        method = None
        try:
            html, js_data = await get_product_page_html(gtin, context)

            if html is None and js_data is None:
                row = _empty_row(gtin, your_price, cost_price, "Not found")
                label = "Not found"
            else:
                if js_data is not None:
                    product_data = extract_from_js_data(js_data)
                    method = "js"
                else:
                    product_data = extract_product_data(html, client=claude_client)
                    method = product_data["extraction_method"]

                scenarios = calculate_all_scenarios(
                    your_price=your_price,
                    cost_price=cost_price,
                    sellers=product_data.get("sellers") or [],
                    margin_divisor=margin_divisor,
                    min_stock=min_stock,
                    low_stock_gap_threshold=low_stock_gap_threshold,
                )

                row = _build_row(gtin, your_price, cost_price, product_data, scenarios, margin_divisor)
                name = (product_data.get("product_name") or "?")[:40]
                sa = scenarios.get("scenario_a") or {}
                label = f"{name} | {sa.get('notes', '')} | A: {sa.get('suggested_price')}"

            async with lock:
                state["results"].append(row)
                state["processed_gtins"].add(gtin)
                if method == "js":
                    state["js_hits"] += 1
                elif method == "bs4":
                    state["bs4_hits"] += 1
                elif method == "claude":
                    state["claude_fallbacks"] += 1
                _save_checkpoint(state)

            print(f"[{i}/{total}] {gtin} → {label}", flush=True)

        except ExtractionError:
            row = _empty_row(gtin, your_price, cost_price, "Extraction failed")
            async with lock:
                state["error_count"] += 1
                state["results"].append(row)
                state["processed_gtins"].add(gtin)
                _save_checkpoint(state)
            print(f"[{i}/{total}] {gtin} → Extraction failed", flush=True)

        except Exception as e:
            row = _empty_row(gtin, your_price, cost_price, f"Error: {str(e)[:80]}")
            async with lock:
                state["error_count"] += 1
                state["results"].append(row)
                state["processed_gtins"].add(gtin)
                _save_checkpoint(state)
            print(f"[{i}/{total}] {gtin} → Error: {str(e)[:60]}", flush=True)


async def _run_pipeline(rows: list, config: dict) -> dict:
    """Shared execution: login → scrape → calculate → write Excel."""
    saved_results, processed_gtins, error_count, js_hits, bs4_hits, claude_fallbacks = _load_checkpoint()
    rows = [r for r in rows if r["gtin"] not in processed_gtins]

    claude_client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    playwright, browser, context = await get_authenticated_context(
        config["qogita_email"],
        config["qogita_password"],
        headless=config["headless"]
    )

    total = len(processed_gtins) + len(rows)
    print(f"Starting analysis: {total} products total, {len(rows)} remaining ({CONCURRENCY} parallel)")

    state = {
        "results": saved_results,
        "processed_gtins": processed_gtins,
        "error_count": error_count,
        "js_hits": js_hits,
        "bs4_hits": bs4_hits,
        "claude_fallbacks": claude_fallbacks,
    }

    semaphore = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()

    try:
        tasks = [
            _process_row(semaphore, lock, sheet_row, i, total, context, claude_client, config, state)
            for i, sheet_row in enumerate(rows, start=len(processed_gtins) + 1)
        ]
        await asyncio.gather(*tasks)
    finally:
        await browser.close()
        await playwright.stop()

    file_path = write_excel(state["results"])
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
    return {
        "file_path": file_path,
        "row_count": len(state["results"]),
        "error_count": state["error_count"],
        "js_hits": state["js_hits"],
        "bs4_hits": state["bs4_hits"],
        "claude_fallbacks": state["claude_fallbacks"],
    }


async def run_analysis_from_excel(excel_path: str, config_path: str = "config.json", limit: int | None = None) -> dict:
    """Pipeline using a local Excel file instead of Google Sheets."""
    config = load_config(config_path)
    rows = read_excel_rows(excel_path)
    if limit is not None:
        rows = rows[:limit]
    return await _run_pipeline(rows, config)


async def run_analysis(config_path: str = "config.json", limit: int | None = None) -> dict:
    """
    Full pipeline: fetch sheet → login → scrape each GTIN → calculate → write Excel.
    Runs up to CONCURRENCY products in parallel.
    Supports resume: if checkpoint.json exists, skips already-processed GTINs.
    """
    config = load_config(config_path)
    rows = fetch_sheet_rows(config["google_sheet_url"])
    if limit is not None:
        rows = rows[:limit]
    return await _run_pipeline(rows, config)

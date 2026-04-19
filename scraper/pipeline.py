import asyncio
import json
import os
import anthropic
from scraper.config_loader import load_config
from scraper.sheet import fetch_sheet_rows
from scraper.auth import get_authenticated_context
from scraper.search import get_product_page_html
from scraper.extractor import extract_product_data, extract_from_js_data, ExtractionError
from scraper.calculator import calculate_row
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

    async with semaphore:
        try:
            html, js_data = await get_product_page_html(gtin, context)

            if html is None and js_data is None:
                row = AnalysisRow(
                    gtin=gtin, product_name=None, your_qogita_price=your_price,
                    cost_price=cost_price, cheapest_seller=None, cheapest_seller_stock=None,
                    cheapest_seller_max_price=None, suggested_price=None, difference=None,
                    notes="Not found"
                )
                label = "Not found"
                method = None
            else:
                if js_data is not None:
                    product_data = extract_from_js_data(js_data)
                    method = "js"
                else:
                    product_data = extract_product_data(html, client=claude_client)
                    method = product_data["extraction_method"]

                pricing = calculate_row(
                    your_price=your_price,
                    cost_price=cost_price,
                    cheapest_max_price=product_data["cheapest_seller_max_price"],
                    margin_divisor=config["margin_divisor"]
                )
                row = AnalysisRow(
                    gtin=gtin,
                    product_name=product_data["product_name"],
                    your_qogita_price=your_price,
                    cost_price=cost_price,
                    cheapest_seller=product_data["cheapest_seller"],
                    cheapest_seller_stock=product_data["cheapest_seller_stock"],
                    cheapest_seller_max_price=product_data["cheapest_seller_max_price"],
                    **pricing
                )
                name = (product_data["product_name"] or "?")[:40]
                label = f"{name} | {pricing['notes']} | suggested: {pricing['suggested_price']}"

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
            row = AnalysisRow(
                gtin=gtin, product_name=None, your_qogita_price=your_price,
                cost_price=cost_price, cheapest_seller=None, cheapest_seller_stock=None,
                cheapest_seller_max_price=None, suggested_price=None, difference=None,
                notes="Extraction failed"
            )
            async with lock:
                state["error_count"] += 1
                state["results"].append(row)
                state["processed_gtins"].add(gtin)
                _save_checkpoint(state)
            print(f"[{i}/{total}] {gtin} → Extraction failed", flush=True)

        except Exception as e:
            row = AnalysisRow(
                gtin=gtin, product_name=None, your_qogita_price=your_price,
                cost_price=cost_price, cheapest_seller=None, cheapest_seller_stock=None,
                cheapest_seller_max_price=None, suggested_price=None, difference=None,
                notes=f"Error: {str(e)[:80]}"
            )
            async with lock:
                state["error_count"] += 1
                state["results"].append(row)
                state["processed_gtins"].add(gtin)
                _save_checkpoint(state)
            print(f"[{i}/{total}] {gtin} → Error: {str(e)[:60]}", flush=True)


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

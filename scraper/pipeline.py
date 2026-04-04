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


def _load_checkpoint() -> tuple[list[AnalysisRow], int, int, int, int, int]:
    if not os.path.exists(CHECKPOINT_PATH):
        return [], 0, 0, 0, 0, 0
    with open(CHECKPOINT_PATH) as f:
        data = json.load(f)
    print(f"Resuming from checkpoint: {data['processed']} products already done")
    return (
        data["results"],
        data["error_count"],
        data["js_hits"],
        data["bs4_hits"],
        data["claude_fallbacks"],
        data["processed"],
    )


def _save_checkpoint(results, error_count, js_hits, bs4_hits, claude_fallbacks):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump({
            "processed": len(results),
            "results": results,
            "error_count": error_count,
            "js_hits": js_hits,
            "bs4_hits": bs4_hits,
            "claude_fallbacks": claude_fallbacks,
        }, f)


async def run_analysis(config_path: str = "config.json", limit: int | None = None) -> dict:
    """
    Full pipeline: fetch sheet → login → scrape each GTIN → calculate → write Excel.
    limit: if set, only process the first N rows (useful for testing).
    Supports resume: if a checkpoint.json exists, skips already-processed products.
    Returns: {"file_path", "row_count", "error_count", "js_hits", "bs4_hits", "claude_fallbacks"}
    """
    config = load_config(config_path)
    rows = fetch_sheet_rows(config["google_sheet_url"])
    if limit is not None:
        rows = rows[:limit]

    results, error_count, js_hits, bs4_hits, claude_fallbacks, start_from = _load_checkpoint()
    rows = rows[start_from:]

    claude_client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    playwright, browser, context = await get_authenticated_context(
        config["qogita_email"],
        config["qogita_password"],
        headless=config["headless"]
    )

    total = start_from + len(rows)
    print(f"Starting analysis: {total} products total, {len(rows)} remaining")

    try:
        for i, sheet_row in enumerate(rows, start=start_from + 1):
            gtin = sheet_row["gtin"]
            your_price = sheet_row["unit_price"]
            cost_price = sheet_row["cost_price"]

            print(f"[{i}/{total}] {gtin}", end=" → ", flush=True)

            try:
                html, js_data = await get_product_page_html(gtin, context)

                if html is None and js_data is None:
                    results.append(AnalysisRow(
                        gtin=gtin,
                        product_name=None,
                        your_qogita_price=your_price,
                        cost_price=cost_price,
                        cheapest_seller=None,
                        cheapest_seller_stock=None,
                        cheapest_seller_max_price=None,
                        suggested_price=None,
                        difference=None,
                        notes="Not found"
                    ))
                    print("Not found")
                    _save_checkpoint(results, error_count, js_hits, bs4_hits, claude_fallbacks)
                    continue

                # Prefer JS extraction (live DOM) → BS4/Claude fallback
                if js_data is not None:
                    product_data = extract_from_js_data(js_data)
                    js_hits += 1
                else:
                    product_data = extract_product_data(html, client=claude_client)
                    if product_data["extraction_method"] == "bs4":
                        bs4_hits += 1
                    else:
                        claude_fallbacks += 1

                pricing = calculate_row(
                    your_price=your_price,
                    cost_price=cost_price,
                    cheapest_max_price=product_data["cheapest_seller_max_price"],
                    margin_divisor=config["margin_divisor"]
                )

                results.append(AnalysisRow(
                    gtin=gtin,
                    product_name=product_data["product_name"],
                    your_qogita_price=your_price,
                    cost_price=cost_price,
                    cheapest_seller=product_data["cheapest_seller"],
                    cheapest_seller_stock=product_data["cheapest_seller_stock"],
                    cheapest_seller_max_price=product_data["cheapest_seller_max_price"],
                    **pricing
                ))
                name = (product_data["product_name"] or "?")[:40]
                print(f"{name} | {pricing['notes']} | suggested: {pricing['suggested_price']}")
                _save_checkpoint(results, error_count, js_hits, bs4_hits, claude_fallbacks)

            except ExtractionError as e:
                error_count += 1
                results.append(AnalysisRow(
                    gtin=gtin,
                    product_name=None,
                    your_qogita_price=your_price,
                    cost_price=cost_price,
                    cheapest_seller=None,
                    cheapest_seller_stock=None,
                    cheapest_seller_max_price=None,
                    suggested_price=None,
                    difference=None,
                    notes="Extraction failed"
                ))
                print("Extraction failed")
                _save_checkpoint(results, error_count, js_hits, bs4_hits, claude_fallbacks)

            except Exception as e:
                error_count += 1
                results.append(AnalysisRow(
                    gtin=gtin,
                    product_name=None,
                    your_qogita_price=your_price,
                    cost_price=cost_price,
                    cheapest_seller=None,
                    cheapest_seller_stock=None,
                    cheapest_seller_max_price=None,
                    suggested_price=None,
                    difference=None,
                    notes=f"Error: {str(e)[:80]}"
                ))
                print(f"Error: {str(e)[:60]}")
                _save_checkpoint(results, error_count, js_hits, bs4_hits, claude_fallbacks)

    finally:
        await browser.close()
        await playwright.stop()

    file_path = write_excel(results)
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
    return {
        "file_path": file_path,
        "row_count": len(results),
        "error_count": error_count,
        "js_hits": js_hits,
        "bs4_hits": bs4_hits,
        "claude_fallbacks": claude_fallbacks,
    }

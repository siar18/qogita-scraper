import asyncio
import anthropic
from scraper.config_loader import load_config
from scraper.sheet import fetch_sheet_rows
from scraper.auth import get_authenticated_context
from scraper.search import get_product_page_html
from scraper.extractor import extract_product_data, ExtractionError
from scraper.calculator import calculate_row
from output.writer import write_excel, AnalysisRow


async def run_analysis(config_path: str = "config.json") -> dict:
    """
    Full pipeline: fetch sheet → login → scrape each GTIN → calculate → write Excel.
    Returns: {"file_path", "row_count", "error_count", "bs4_hits", "claude_fallbacks"}
    """
    config = load_config(config_path)
    rows = fetch_sheet_rows(config["google_sheet_url"])

    claude_client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    playwright, browser, context = await get_authenticated_context(
        config["qogita_email"],
        config["qogita_password"],
        headless=config["headless"]
    )

    results: list[AnalysisRow] = []
    error_count = 0
    bs4_hits = 0
    claude_fallbacks = 0

    try:
        for sheet_row in rows:
            gtin = sheet_row["gtin"]
            your_price = sheet_row["unit_price"]
            cost_price = sheet_row["cost_price"]

            try:
                html = await get_product_page_html(gtin, context)

                if html is None:
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
                    continue

                product_data = extract_product_data(html, client=claude_client)

                # Track which extraction method was used
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

    finally:
        await browser.close()
        await playwright.stop()

    file_path = write_excel(results)
    return {
        "file_path": file_path,
        "row_count": len(results),
        "error_count": error_count,
        "bs4_hits": bs4_hits,
        "claude_fallbacks": claude_fallbacks,
    }

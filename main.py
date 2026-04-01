import asyncio
import json
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("qogita-scraper")

_last_run_state: dict = {
    "last_run": None,
    "file_path": None,
    "row_count": None,
    "error_count": None,
}


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_full_analysis",
            description="Fetch the Google Sheet, scrape all GTINs on Qogita, and write a dated Excel analysis file.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_product_price",
            description="Scrape pricing for a single product by GTIN and return structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "gtin": {"type": "string", "description": "The product GTIN/EAN code"}
                },
                "required": ["gtin"]
            }
        ),
        types.Tool(
            name="get_analysis_status",
            description="Get metadata about the last analysis run.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    from scraper.pipeline import run_analysis
    from scraper.config_loader import load_config
    from scraper.auth import get_authenticated_context
    from scraper.search import get_product_page_html
    from scraper.extractor import extract_product_data
    from scraper.calculator import calculate_row
    import anthropic

    if name == "run_full_analysis":
        result = await run_analysis()
        _last_run_state.update({
            "last_run": datetime.now().isoformat(),
            **result
        })
        return [types.TextContent(
            type="text",
            text=json.dumps(result)
        )]

    elif name == "get_product_price":
        gtin = arguments["gtin"]
        config = load_config()
        playwright, browser, context = await get_authenticated_context(
            config["qogita_email"], config["qogita_password"], config["headless"]
        )
        try:
            html = await get_product_page_html(gtin, context)
            if html is None:
                result = {"gtin": gtin, "notes": "Not found"}
            else:
                client = anthropic.Anthropic()
                product_data = extract_product_data(html, client=client)
                pricing = calculate_row(
                    your_price=0,  # no sheet price available for single lookup
                    cost_price=0,
                    cheapest_max_price=product_data["cheapest_seller_max_price"],
                    margin_divisor=config["margin_divisor"]
                )
                result = {**product_data, **pricing, "gtin": gtin}
        finally:
            await browser.close()
            await playwright.stop()

        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "get_analysis_status":
        return [types.TextContent(type="text", text=json.dumps(_last_run_state))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

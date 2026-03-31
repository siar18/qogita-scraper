# Qogita Scraper — Design Spec
**Date:** 2026-04-01

## Overview

An MCP server that scrapes Qogita.com for pricing data on products in the user's Google Sheet stockfile. For each product (identified by GTIN), it finds the cheapest seller's highest-tier price, calculates a suggested competitive selling price, and compares it to the user's current Qogita listing price. Results are saved to a dated Excel file.

---

## Architecture

```
qogita-scraper/
├── config.json              # credentials + constants
├── main.py                  # MCP server entry point, registers tools
├── scraper/
│   ├── auth.py              # Playwright login + session persistence
│   ├── search.py            # Search by GTIN, navigate to product page
│   ├── extractor.py         # Claude-powered HTML → structured data extraction
│   └── sheet.py             # Fetch Google Sheet → list of {gtin, unit_price}
├── output/
│   └── writer.py            # Build and save Excel file
└── requirements.txt
```

---

## Config (`config.json`)

```json
{
  "qogita_email": "your@email.com",
  "qogita_password": "yourpassword",
  "google_sheet_url": "https://docs.google.com/spreadsheets/...",
  "margin_divisor": 1.12,
  "headless": true
}
```

- `margin_divisor`: used to calculate suggested price. Default 1.12. Configurable.
- `headless`: set to `false` for debugging (shows browser window).

---

## MCP Tools

### `run_full_analysis`
Fetches the Google Sheet, scrapes all GTINs on Qogita, and writes the Excel file.
- **Returns:** file path of the saved Excel file, row count, error count.

### `get_product_price(gtin: str)`
Scrapes a single product by GTIN and returns structured pricing data.
- **Returns:** product name, cheapest seller, cheapest seller max price, suggested price, notes.

### `get_analysis_status`
Returns metadata about the last run.
- **Returns:** last run timestamp, row count, output file path, any errors encountered.

---

## Data Flow

1. **Fetch sheet** — Download the public Google Sheet as XLSX. Read all rows, extract GTIN (col 2, "GTIN") and Unit Price (col 5, "Unit Price").
2. **Login** — Playwright logs in to Qogita using credentials from config. Session is persisted (browser storage state saved) to avoid re-login on every run.
3. **Search** — For each GTIN, type it into the Qogita search bar and click the first result.
4. **Scrape** — Capture the "Lowest priced offer" section HTML from the product page.
5. **Extract (Claude-powered)** — Pass the HTML snippet to Claude (via Anthropic SDK). Claude returns: product name, cheapest supplier name, list of unit price tiers. This step is resilient to HTML/CSS changes — no fragile selectors.
6. **Calculate**:
   - `cheapest_seller_max_price` = highest price tier of the cheapest seller (e.g. €60.28 — the price at lowest MOV)
   - `suggested_price` = `cheapest_seller_max_price ÷ margin_divisor`
   - `difference` = `suggested_price − your_qogita_price`
   - If `suggested_price < your_unit_price` → Notes: "Can't compete"
   - If product not found → Notes: "Not found"
   - If already competitive (difference ≥ 0) → Notes: "Already competitive"
   - Otherwise → Notes: "Lower needed"
7. **Write Excel** — Save to `output/YYYY-MM-DD_qogita_products_analysis.xlsx`.

---

## Output Excel Columns

| Column | Description |
|--------|-------------|
| GTIN | Product GTIN from Google Sheet |
| Product Name | Scraped from Qogita product page |
| Your Qogita Price | Unit Price from Google Sheet (col 5) |
| Cheapest Seller | Supplier name of the lowest-priced offer |
| Cheapest Seller Max Price | Highest price tier (lowest MOV) of cheapest seller |
| Suggested Price | Cheapest Seller Max Price ÷ 1.12 |
| Difference | Suggested Price − Your Qogita Price (negative = need to lower) |
| Notes | Status: OK / Lower needed / Can't compete / Not found |

---

## Error Handling

- **Product not found on Qogita:** Notes = "Not found", price columns left blank.
- **Login failure:** Abort run, raise error with message.
- **Extraction failure (Claude can't parse):** Notes = "Extraction failed", log raw HTML for debugging.
- **Sheet fetch failure:** Abort run, raise error with message.
- **Rate limiting / timeout:** Retry up to 3 times with a 5-second delay before marking as failed.

---

## Daily Runs

The MCP tool `run_full_analysis` can be scheduled via:
- **Mac cron:** `0 8 * * * cd /Users/siar/Projects/qogita-scraper && python main.py run`
- **Claude Code:** Call `run_full_analysis` tool from any agent at any time.

Each run produces a new dated Excel file, preserving history.

---

## Dependencies

- `playwright` — browser automation
- `anthropic` — Claude-powered HTML extraction
- `openpyxl` — Excel file writing
- `requests` / `pandas` — Google Sheet download and parsing
- `mcp` — MCP server framework (Anthropic Python SDK)

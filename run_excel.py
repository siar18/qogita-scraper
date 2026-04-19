"""
Standalone runner — no Claude/MCP needed.

Usage:
    python3 run_excel.py /path/to/your_products.xlsx
    python3 run_excel.py /path/to/your_products.xlsx --limit 10
"""
import asyncio
import sys
import argparse
from scraper.pipeline import run_analysis_from_excel


def main():
    parser = argparse.ArgumentParser(description="Run Qogita analysis from a local Excel file.")
    parser.add_argument("excel_path", help="Path to your Excel file with EAN and cost price columns")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N products (useful for testing)")
    args = parser.parse_args()

    print(f"Running analysis from: {args.excel_path}")
    result = asyncio.run(run_analysis_from_excel(excel_path=args.excel_path, limit=args.limit))

    print("\n--- Done ---")
    print(f"Output file : {result['file_path']}")
    print(f"Products    : {result['row_count']}")
    print(f"Errors      : {result['error_count']}")


if __name__ == "__main__":
    main()

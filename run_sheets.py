"""
Standalone runner for Google Sheets — no Claude/MCP needed.
Reads your product list from the Google Sheets URL in config.json.

Usage:
    python3 run_sheets.py
    python3 run_sheets.py --limit 10
"""
import asyncio
import argparse
from scraper.pipeline import run_analysis


def main():
    parser = argparse.ArgumentParser(description="Run Qogita analysis from Google Sheets (your full inventory).")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N products (useful for testing)")
    args = parser.parse_args()

    print("Running analysis from Google Sheets (config.json)...")
    result = asyncio.run(run_analysis(limit=args.limit))

    print("\n--- Done ---")
    print(f"Output file : {result['file_path']}")
    print(f"Products    : {result['row_count']}")
    print(f"Errors      : {result['error_count']}")


if __name__ == "__main__":
    main()

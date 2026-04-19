import io
from typing import TypedDict
import requests
import pandas as pd


class SheetRow(TypedDict):
    gtin: str
    unit_price: float
    cost_price: float


# Column name aliases (case-insensitive) for Excel file input
_GTIN_ALIASES = {"ean", "gtin", "barcode", "ean code", "ean13", "ean-13", "artikel", "article"}
_COST_ALIASES = {"cost price", "cost_price", "inkoopprijs", "purchase price", "costprice", "inkoop", "cost"}
_PRICE_ALIASES = {"your price", "unit price", "verkoopprijs", "sale price", "price", "jouw prijs", "selling price"}


def read_excel_rows(file_path: str) -> list[SheetRow]:
    """Read products from a local Excel file.

    The file must have a header row with at least:
      - An EAN/GTIN column  (see _GTIN_ALIASES for accepted names)
      - A cost price column (see _COST_ALIASES for accepted names)
    Optionally:
      - A 'your price' column (see _PRICE_ALIASES). Defaults to 0.0 if absent.

    Raises ValueError if required columns cannot be found.
    """
    df = pd.read_excel(file_path, dtype=str)

    # Normalise column names for matching
    col_map: dict[str, str] = {c.strip().lower(): c for c in df.columns}

    def _find_col(aliases: set[str]) -> str | None:
        for alias in aliases:
            if alias in col_map:
                return col_map[alias]
        return None

    gtin_col = _find_col(_GTIN_ALIASES)
    cost_col = _find_col(_COST_ALIASES)
    price_col = _find_col(_PRICE_ALIASES)

    if gtin_col is None:
        raise ValueError(
            f"Could not find an EAN/GTIN column in '{file_path}'. "
            f"Expected one of: {sorted(_GTIN_ALIASES)}. Found: {list(df.columns)}"
        )
    if cost_col is None:
        raise ValueError(
            f"Could not find a cost price column in '{file_path}'. "
            f"Expected one of: {sorted(_COST_ALIASES)}. Found: {list(df.columns)}"
        )

    rows: list[SheetRow] = []
    for _, row in df.iterrows():
        gtin = str(row[gtin_col]).strip() if pd.notna(row[gtin_col]) else None
        if not gtin or gtin.lower() == "nan":
            continue
        try:
            cost_price = float(str(row[cost_col]).replace(",", "."))
        except ValueError:
            continue
        unit_price = 0.0
        if price_col is not None:
            try:
                unit_price = float(str(row[price_col]).replace(",", "."))
            except ValueError:
                pass
        gtin = gtin.zfill(13)
        rows.append(SheetRow(gtin=gtin, unit_price=unit_price, cost_price=cost_price))

    return rows


def fetch_sheet_rows(url: str) -> list[SheetRow]:
    response = requests.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to download Google Sheet (HTTP {response.status_code})")

    df = pd.read_excel(io.BytesIO(response.content), header=None, dtype=str)

    rows: list[SheetRow] = []
    for _, row in df.iterrows():
        gtin = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None
        if not gtin or gtin.lower() == "nan":
            continue
        try:
            unit_price = float(str(row.iloc[4]).replace(",", "."))
            cost_price = float(str(row.iloc[5]).replace(",", "."))
        except (ValueError, IndexError):
            continue
        # Pad GTIN to 13 digits with leading zeros (EAN-13 standard)
        gtin = gtin.zfill(13)
        rows.append(SheetRow(gtin=gtin, unit_price=unit_price, cost_price=cost_price))

    return rows

import io
from typing import TypedDict
import requests
import pandas as pd


class SheetRow(TypedDict):
    gtin: str
    unit_price: float
    cost_price: float


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

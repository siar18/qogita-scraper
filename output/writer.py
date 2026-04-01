import os
from datetime import date
from typing import Optional, TypedDict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


class AnalysisRow(TypedDict):
    gtin: str
    product_name: Optional[str]
    your_qogita_price: float
    cost_price: float
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]
    suggested_price: Optional[float]
    difference: Optional[float]
    notes: str


HEADERS = [
    "GTIN", "Product Name", "Your Qogita Price", "Cost Price",
    "Cheapest Seller", "Cheapest Seller Max Price",
    "Suggested Price", "Difference", "Notes"
]

NOTE_COLORS = {
    "Lower needed": "FFFFC0",      # yellow
    "Can't compete": "FFCCCC",     # red
    "Already competitive": "CCFFCC",  # green
    "Not found": "E0E0E0",         # grey
    "Extraction failed": "FFD9B3", # orange
}


def write_excel(rows: list[AnalysisRow], output_dir: str = "output") -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{date.today().strftime('%Y-%m-%d')}_qogita_products_analysis.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analysis"

    # Header row
    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        values = [
            row["gtin"],
            row.get("product_name"),
            row["your_qogita_price"],
            row["cost_price"],
            row.get("cheapest_seller"),
            row.get("cheapest_seller_max_price"),
            row.get("suggested_price"),
            row.get("difference"),
            row["notes"],
        ]
        for col, value in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col, value=value)

        # Color the Notes cell
        notes = row["notes"]
        color = NOTE_COLORS.get(notes)
        if color:
            ws.cell(row=row_idx, column=9).fill = PatternFill("solid", fgColor=color)

    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

    wb.save(filepath)
    return filepath

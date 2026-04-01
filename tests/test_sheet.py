import pytest
import pandas as pd
import io
from unittest.mock import patch, MagicMock
from scraper.sheet import fetch_sheet_rows, SheetRow


def make_mock_xlsx():
    """Create a minimal in-memory XLSX with the right columns."""
    df = pd.DataFrame({
        0: ["ignore"],          # col A
        1: ["3614272225718"],   # col B = GTIN
        2: ["ignore"],
        3: ["ignore"],
        4: [60.00],             # col E = Unit Price
        5: [45.00],             # col F = Cost Price
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False)
    buf.seek(0)
    return buf.read()


def test_fetch_sheet_rows_returns_list_of_sheet_rows():
    with patch("scraper.sheet.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = make_mock_xlsx()
        mock_get.return_value = mock_resp

        rows = fetch_sheet_rows("https://fake.url/sheet")

    assert len(rows) == 1
    assert rows[0]["gtin"] == "3614272225718"
    assert rows[0]["unit_price"] == 60.00
    assert rows[0]["cost_price"] == 45.00


def test_fetch_sheet_rows_skips_rows_missing_gtin():
    df = pd.DataFrame({
        0: [None], 1: [None], 2: [None], 3: [None], 4: [50.0], 5: [30.0]
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False)
    buf.seek(0)

    with patch("scraper.sheet.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = buf.read()
        mock_get.return_value = mock_resp

        rows = fetch_sheet_rows("https://fake.url/sheet")

    assert rows == []


def test_fetch_sheet_rows_raises_on_http_error():
    with patch("scraper.sheet.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        with pytest.raises(RuntimeError, match="Failed to download"):
            fetch_sheet_rows("https://fake.url/sheet")

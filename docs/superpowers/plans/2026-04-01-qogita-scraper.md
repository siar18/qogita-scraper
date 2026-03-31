# Qogita Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that scrapes Qogita.com pricing for products in a Google Sheet and outputs a dated Excel analysis file with suggested competitive prices.

**Architecture:** Playwright handles browser login and navigation; Claude (Anthropic SDK) extracts pricing data from raw HTML so the scraper self-adapts to page layout changes. An MCP server wraps everything into callable tools usable by Claude agents.

**Tech Stack:** Python 3.11+, Playwright, Anthropic SDK, `mcp` (Python SDK), `openpyxl`, `pandas`, `requests`

---

## File Map

| File | Responsibility |
|------|---------------|
| `config.json` | Credentials and constants (email, password, sheet URL, margin_divisor, headless) |
| `config.example.json` | Safe committed example config (no real credentials) |
| `requirements.txt` | Python dependencies |
| `scraper/sheet.py` | Download Google Sheet XLSX, return list of `SheetRow` dicts |
| `scraper/auth.py` | Playwright login, session persistence to `session_state.json` |
| `scraper/search.py` | Search Qogita by GTIN, return product page HTML |
| `scraper/extractor.py` | Claude-powered HTML → `ProductData` typed dict |
| `scraper/calculator.py` | Pure pricing logic: suggested price, difference, notes |
| `output/writer.py` | Build and save Excel file with proper columns |
| `main.py` | MCP server entry point, registers tools, tracks run state |
| `tests/test_sheet.py` | Tests for sheet parsing |
| `tests/test_extractor.py` | Tests for Claude extraction (mocked) |
| `tests/test_calculator.py` | Tests for pricing logic |
| `tests/test_writer.py` | Tests for Excel output |

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `config.example.json`
- Create: `config.json` (gitignored)
- Create: `.gitignore`

- [ ] **Step 1: Create requirements.txt**

```
playwright==1.44.0
anthropic>=0.28.0
mcp>=1.0.0
openpyxl>=3.1.0
pandas>=2.0.0
requests>=2.31.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Create config.example.json**

```json
{
  "qogita_email": "your@email.com",
  "qogita_password": "yourpassword",
  "google_sheet_url": "https://docs.google.com/spreadsheets/d/e/YOUR_SHEET_ID/pub?output=xlsx",
  "margin_divisor": 1.12,
  "headless": true
}
```

- [ ] **Step 3: Create config.json with real credentials**

```json
{
  "qogita_email": "FILL_IN",
  "qogita_password": "FILL_IN",
  "google_sheet_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSci-GKyiTzH1SC3LraedC450Bucz_eHwNIDvs0lstldK0NE-vcduwI1V9uHGBM4TxkgI0TP62BhjvD/pub?output=xlsx",
  "margin_divisor": 1.12,
  "headless": true
}
```

- [ ] **Step 4: Create .gitignore**

```
config.json
session_state.json
output/
__pycache__/
.pytest_cache/
*.pyc
```

- [ ] **Step 5: Create package structure**

```bash
mkdir -p scraper output tests
touch scraper/__init__.py output/__init__.py tests/__init__.py
```

- [ ] **Step 6: Install dependencies**

```bash
cd /Users/siar/Projects/qogita-scraper
pip install -r requirements.txt
playwright install chromium
```

Expected: All packages install without error. `playwright install chromium` downloads ~170MB.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt config.example.json .gitignore scraper/__init__.py output/__init__.py tests/__init__.py
git commit -m "feat: project scaffold and dependencies"
```

---

## Task 2: Config Loader

**Files:**
- Create: `scraper/config_loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_loader.py`:

```python
import json
import os
import pytest
from scraper.config_loader import load_config, ConfigError


def test_load_config_returns_all_fields(tmp_path):
    cfg = {
        "qogita_email": "test@test.com",
        "qogita_password": "secret",
        "google_sheet_url": "https://example.com/sheet",
        "margin_divisor": 1.12,
        "headless": True
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg))
    result = load_config(str(config_file))
    assert result["qogita_email"] == "test@test.com"
    assert result["margin_divisor"] == 1.12
    assert result["headless"] is True


def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.json")


def test_load_config_missing_required_field_raises(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"qogita_email": "x@x.com"}))
    with pytest.raises(ConfigError, match="qogita_password"):
        load_config(str(config_file))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/siar/Projects/qogita-scraper
pytest tests/test_config_loader.py -v
```

Expected: `ImportError` — `scraper.config_loader` does not exist yet.

- [ ] **Step 3: Implement config_loader.py**

Create `scraper/config_loader.py`:

```python
import json
import os

REQUIRED_FIELDS = ["qogita_email", "qogita_password", "google_sheet_url", "margin_divisor", "headless"]


class ConfigError(Exception):
    pass


def load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        config = json.load(f)
    for field in REQUIRED_FIELDS:
        if field not in config:
            raise ConfigError(f"Missing required config field: {field}")
    return config
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config_loader.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/config_loader.py tests/test_config_loader.py
git commit -m "feat: config loader with validation"
```

---

## Task 3: Google Sheet Fetcher

**Files:**
- Create: `scraper/sheet.py`
- Create: `tests/test_sheet.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sheet.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_sheet.py -v
```

Expected: `ImportError` — `scraper.sheet` does not exist yet.

- [ ] **Step 3: Implement sheet.py**

Create `scraper/sheet.py`:

```python
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
        rows.append(SheetRow(gtin=gtin, unit_price=unit_price, cost_price=cost_price))

    return rows
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_sheet.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/sheet.py tests/test_sheet.py
git commit -m "feat: google sheet fetcher"
```

---

## Task 4: Pricing Calculator

**Files:**
- Create: `scraper/calculator.py`
- Create: `tests/test_calculator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calculator.py`:

```python
from scraper.calculator import calculate_row, PricingResult


def test_lower_needed():
    result = calculate_row(
        your_price=65.00,
        cost_price=45.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    assert result["suggested_price"] == round(60.28 / 1.12, 2)
    assert result["difference"] == round(result["suggested_price"] - 65.00, 2)
    assert result["notes"] == "Lower needed"


def test_already_competitive():
    result = calculate_row(
        your_price=50.00,
        cost_price=40.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    assert result["notes"] == "Already competitive"


def test_cant_compete():
    result = calculate_row(
        your_price=65.00,
        cost_price=55.00,
        cheapest_max_price=60.28,
        margin_divisor=1.12
    )
    # suggested = 60.28/1.12 = 53.82, which is below cost_price 55.00
    assert result["suggested_price"] == round(60.28 / 1.12, 2)
    assert result["notes"] == "Can't compete"


def test_not_found():
    result = calculate_row(
        your_price=65.00,
        cost_price=45.00,
        cheapest_max_price=None,
        margin_divisor=1.12
    )
    assert result["suggested_price"] is None
    assert result["difference"] is None
    assert result["notes"] == "Not found"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_calculator.py -v
```

Expected: `ImportError` — `scraper.calculator` does not exist yet.

- [ ] **Step 3: Implement calculator.py**

Create `scraper/calculator.py`:

```python
from typing import TypedDict, Optional


class PricingResult(TypedDict):
    suggested_price: Optional[float]
    difference: Optional[float]
    notes: str


def calculate_row(
    your_price: float,
    cost_price: float,
    cheapest_max_price: Optional[float],
    margin_divisor: float,
) -> PricingResult:
    if cheapest_max_price is None:
        return PricingResult(suggested_price=None, difference=None, notes="Not found")

    suggested_price = round(cheapest_max_price / margin_divisor, 2)

    if suggested_price < cost_price:
        return PricingResult(
            suggested_price=suggested_price,
            difference=round(suggested_price - your_price, 2),
            notes="Can't compete"
        )

    difference = round(suggested_price - your_price, 2)
    notes = "Already competitive" if difference >= 0 else "Lower needed"

    return PricingResult(suggested_price=suggested_price, difference=difference, notes=notes)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_calculator.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/calculator.py tests/test_calculator.py
git commit -m "feat: pricing calculator with margin and competition logic"
```

---

## Task 5: Excel Writer

**Files:**
- Create: `output/writer.py`
- Create: `tests/test_writer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_writer.py`:

```python
import os
from datetime import date
from output.writer import write_excel, AnalysisRow


def test_write_excel_creates_file(tmp_path):
    rows = [
        AnalysisRow(
            gtin="3614272225718",
            product_name="Giorgio Armani Stronger With You 100ml",
            your_qogita_price=65.00,
            cost_price=45.00,
            cheapest_seller="2WYZL",
            cheapest_seller_max_price=60.28,
            suggested_price=53.82,
            difference=-11.18,
            notes="Lower needed"
        )
    ]
    output_path = write_excel(rows, output_dir=str(tmp_path))
    assert os.path.exists(output_path)
    assert date.today().strftime("%Y-%m-%d") in output_path


def test_write_excel_correct_columns(tmp_path):
    import openpyxl
    rows = [
        AnalysisRow(
            gtin="123",
            product_name="Test Product",
            your_qogita_price=50.0,
            cost_price=30.0,
            cheapest_seller=None,
            cheapest_seller_max_price=None,
            suggested_price=None,
            difference=None,
            notes="Not found"
        )
    ]
    output_path = write_excel(rows, output_dir=str(tmp_path))
    wb = openpyxl.load_workbook(output_path)
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    assert headers == [
        "GTIN", "Product Name", "Your Qogita Price", "Cost Price",
        "Cheapest Seller", "Cheapest Seller Max Price",
        "Suggested Price", "Difference", "Notes"
    ]
    assert ws.cell(2, 9).value == "Not found"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_writer.py -v
```

Expected: `ImportError` — `output.writer` does not exist yet.

- [ ] **Step 3: Implement writer.py**

Create `output/writer.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_writer.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add output/writer.py tests/test_writer.py
git commit -m "feat: excel writer with color-coded notes column"
```

---

## Task 6: Claude-Powered Extractor

**Files:**
- Create: `scraper/extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_extractor.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from scraper.extractor import extract_product_data, ProductData, ExtractionError


SAMPLE_HTML = """
<h1>Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml</h1>
<div>
  <p class="font-medium">Unit price</p>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€56.12</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€57.28</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€58.30</span>
  <span class="whitespace-nowrap text-sm md:ml-auto font-light">€60.28</span>
  <p class="font-medium">Supplier: 2WYZL</p>
</div>
"""

MOCK_CLAUDE_RESPONSE = '{"product_name": "Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml", "cheapest_seller": "2WYZL", "price_tiers": [56.12, 57.28, 58.30, 60.28]}'


def test_extract_product_data_returns_product_data():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=MOCK_CLAUDE_RESPONSE)]
    )
    result = extract_product_data(SAMPLE_HTML, client=mock_client)
    assert result["product_name"] == "Giorgio Armani Stronger With You Intensely Eau De Parfum Spray 100ml"
    assert result["cheapest_seller"] == "2WYZL"
    assert result["cheapest_seller_max_price"] == 60.28


def test_extract_returns_none_when_not_found():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"product_name": null, "cheapest_seller": null, "price_tiers": []}')]
    )
    result = extract_product_data("<html>No product here</html>", client=mock_client)
    assert result["cheapest_seller"] is None
    assert result["cheapest_seller_max_price"] is None


def test_extract_raises_on_invalid_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Sorry I cannot help with that")]
    )
    with pytest.raises(ExtractionError):
        extract_product_data(SAMPLE_HTML, client=mock_client)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_extractor.py -v
```

Expected: `ImportError` — `scraper.extractor` does not exist yet.

- [ ] **Step 3: Implement extractor.py**

Create `scraper/extractor.py`:

```python
import json
from typing import Optional, TypedDict
import anthropic


class ProductData(TypedDict):
    product_name: Optional[str]
    cheapest_seller: Optional[str]
    cheapest_seller_max_price: Optional[float]


class ExtractionError(Exception):
    pass


EXTRACTION_PROMPT = """You are a data extraction assistant. Given HTML from a Qogita product page, extract:
1. The product name (from the page heading)
2. The name of the cheapest/lowest-priced supplier (labeled "Lowest priced offer")
3. All unit price tiers for that cheapest supplier, as a list of floats

Return ONLY valid JSON in this exact format:
{
  "product_name": "string or null",
  "cheapest_seller": "string or null",
  "price_tiers": [float, float, ...]
}

If the product is not found or no offers exist, return:
{"product_name": null, "cheapest_seller": null, "price_tiers": []}

Do not include any explanation. Only return the JSON object."""


def extract_product_data(html: str, client: anthropic.Anthropic = None) -> ProductData:
    if client is None:
        client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\nHTML:\n{html[:8000]}"
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ExtractionError(f"Claude returned non-JSON response: {raw[:200]}")

    price_tiers: list[float] = data.get("price_tiers", [])
    cheapest_seller_max_price = max(price_tiers) if price_tiers else None

    return ProductData(
        product_name=data.get("product_name"),
        cheapest_seller=data.get("cheapest_seller"),
        cheapest_seller_max_price=cheapest_seller_max_price,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_extractor.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/extractor.py tests/test_extractor.py
git commit -m "feat: claude-powered HTML extractor"
```

---

## Task 7: Playwright Auth + Search

**Files:**
- Create: `scraper/auth.py`
- Create: `scraper/search.py`

> Note: These use Playwright and hit a live website — no unit tests. Manual verification at end of task.

- [ ] **Step 1: Implement auth.py**

Create `scraper/auth.py`:

```python
import os
import json
import asyncio
from playwright.async_api import async_playwright, BrowserContext

SESSION_FILE = "session_state.json"
QOGITA_LOGIN_URL = "https://www.qogita.com/login"


async def get_authenticated_context(email: str, password: str, headless: bool = True) -> tuple:
    """Returns (playwright, browser, context). Caller must close all three."""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=headless)

    if os.path.exists(SESSION_FILE):
        context = await browser.new_context(storage_state=SESSION_FILE)
        page = await context.new_page()
        await page.goto("https://www.qogita.com")
        # Check if still logged in
        if await page.locator("[data-testid='user-menu'], [href='/account']").count() > 0:
            await page.close()
            return playwright, browser, context
        await page.close()
        await context.close()

    # Fresh login
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(QOGITA_LOGIN_URL)
    await page.fill("input[type='email']", email)
    await page.fill("input[type='password']", password)
    await page.click("button[type='submit']")
    await page.wait_for_url("**/catalog**", timeout=15000)
    await context.storage_state(path=SESSION_FILE)
    await page.close()
    return playwright, browser, context
```

- [ ] **Step 2: Implement search.py**

Create `scraper/search.py`:

```python
import asyncio
from playwright.async_api import BrowserContext

QOGITA_BASE = "https://www.qogita.com"
SEARCH_URL = "https://www.qogita.com/catalog?query={gtin}"


async def get_product_page_html(gtin: str, context: BrowserContext, retries: int = 3) -> str | None:
    """
    Navigate to Qogita product page for a GTIN.
    Returns the full page HTML, or None if not found.
    """
    for attempt in range(retries):
        try:
            page = await context.new_page()
            url = SEARCH_URL.format(gtin=gtin)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Click first product result
            first_result = page.locator("a[href*='/products/']").first
            count = await first_result.count()
            if count == 0:
                await page.close()
                return None

            await first_result.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            html = await page.content()
            await page.close()
            return html

        except Exception as e:
            await page.close()
            if attempt == retries - 1:
                raise
            await asyncio.sleep(5)

    return None
```

- [ ] **Step 3: Manual smoke test**

Create a temporary `smoke_test.py` at project root to verify login and search work:

```python
import asyncio
from scraper.config_loader import load_config
from scraper.auth import get_authenticated_context
from scraper.search import get_product_page_html

async def main():
    config = load_config()
    playwright, browser, context = await get_authenticated_context(
        config["qogita_email"], config["qogita_password"], headless=False
    )
    html = await get_product_page_html("3614272225718", context)
    print("Got HTML length:", len(html) if html else "NOT FOUND")
    print(html[:500] if html else "")
    await browser.close()
    await playwright.stop()

asyncio.run(main())
```

Run it:

```bash
python smoke_test.py
```

Expected: Browser opens, logs in, navigates to Giorgio Armani product page, prints HTML length > 5000. Session saved to `session_state.json`.

- [ ] **Step 4: Remove smoke test and commit**

```bash
rm smoke_test.py
git add scraper/auth.py scraper/search.py
git commit -m "feat: playwright auth and product search"
```

---

## Task 8: Full Analysis Pipeline

**Files:**
- Create: `scraper/pipeline.py`

- [ ] **Step 1: Implement pipeline.py**

Create `scraper/pipeline.py`:

```python
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
    Returns: {"file_path": str, "row_count": int, "error_count": int}
    """
    config = load_config(config_path)
    rows = fetch_sheet_rows(config["google_sheet_url"])

    claude_client = anthropic.Anthropic()
    playwright, browser, context = await get_authenticated_context(
        config["qogita_email"],
        config["qogita_password"],
        headless=config["headless"]
    )

    results: list[AnalysisRow] = []
    error_count = 0

    try:
        for sheet_row in rows:
            gtin = sheet_row["gtin"]
            your_price = sheet_row["unit_price"]
            cost_price = sheet_row["cost_price"]

            try:
                html = await get_product_page_html(gtin, context)

                if html is None:
                    pricing = {"suggested_price": None, "difference": None, "notes": "Not found"}
                    results.append(AnalysisRow(
                        gtin=gtin,
                        product_name=None,
                        your_qogita_price=your_price,
                        cost_price=cost_price,
                        cheapest_seller=None,
                        cheapest_seller_max_price=None,
                        **pricing
                    ))
                    continue

                product_data = extract_product_data(html, client=claude_client)
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
                    cheapest_seller_max_price=None,
                    suggested_price=None,
                    difference=None,
                    notes=f"Error: {str(e)[:80]}"
                ))

    finally:
        await browser.close()
        await playwright.stop()

    file_path = write_excel(results)
    return {"file_path": file_path, "row_count": len(results), "error_count": error_count}
```

- [ ] **Step 2: Commit**

```bash
git add scraper/pipeline.py
git commit -m "feat: full analysis pipeline"
```

---

## Task 9: MCP Server

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

Create `main.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: MCP server with run_full_analysis, get_product_price, get_analysis_status tools"
```

---

## Task 10: MCP Registration & End-to-End Verification

**Files:**
- Modify: `~/.claude/claude_desktop_config.json` (or Claude Code MCP settings)

- [ ] **Step 1: Register the MCP server in Claude Code**

Add to your Claude Code MCP config (run `claude mcp add` or edit `~/.claude/claude_desktop_config.json`):

```bash
claude mcp add qogita-scraper python /Users/siar/Projects/qogita-scraper/main.py
```

Or manually add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "qogita-scraper": {
      "command": "python",
      "args": ["/Users/siar/Projects/qogita-scraper/main.py"],
      "cwd": "/Users/siar/Projects/qogita-scraper"
    }
  }
}
```

- [ ] **Step 2: Run all unit tests**

```bash
cd /Users/siar/Projects/qogita-scraper
pytest tests/ -v
```

Expected: All tests pass (config_loader, sheet, calculator, writer, extractor).

- [ ] **Step 3: End-to-end test via MCP tool**

In Claude Code, call:
```
run_full_analysis
```

Expected:
- Browser opens (or runs headless)
- Logs in to Qogita
- Scrapes products from your Google Sheet
- Returns `{"file_path": "output/2026-04-01_qogita_products_analysis.xlsx", "row_count": N, "error_count": 0}`
- Open the file and verify columns, colors, and prices look correct.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: end-to-end verified qogita scraper MCP server"
```

---

## Daily Run (Optional Cron Setup)

To run automatically every morning at 8am, add to crontab:

```bash
crontab -e
```

Add:
```
0 8 * * * cd /Users/siar/Projects/qogita-scraper && python -c "import asyncio; from scraper.pipeline import run_analysis; asyncio.run(run_analysis())" >> /tmp/qogita_cron.log 2>&1
```

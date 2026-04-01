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

import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    # Set headless=False so it opens a real browser window on your screen
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width":1920,"height":1080})
    page = context.new_page()
    page.goto("https://www.coinglass.com/login")
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("singhkaranbir0248@gmail.com")
    page.get_by_role("textbox", name="Email").press("Tab")
    page.get_by_role("textbox", name="Password").click()
    page.get_by_role("textbox", name="Password").fill("Lu$er2hero")
    page.get_by_role("button", name="Login").nth(1).click()
    
    # Wait for the login state to settle
    page.wait_for_timeout(5000)
    
    page1 = context.new_page()
    page1.goto("https://www.coinglass.com/tv/layout/s9")
    
    # Wait for page layout elements to mount
    page1.wait_for_timeout(5000)
    
    page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3).click()
    page1.get_by_role("menuitem", name="Load Chart Layout").click()
    page1.get_by_role("button", name="L_1").click()
    
    # Keep the browser open for 15 seconds so you can watch the loaded layout
    page1.wait_for_timeout(15000)

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

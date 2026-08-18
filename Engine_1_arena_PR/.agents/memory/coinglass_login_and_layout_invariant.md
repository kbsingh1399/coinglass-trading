# CoinGlass Scraper Authentication & Layout Invariant

## ⛔ CRITICAL INVARIANT: DO NOT MODIFY OR REFACTOR THIS FLOW

The CoinGlass UI authentication, layout loading, and 15-minute timeframe enforcement sequence is **100% verified and immutable**.

### Flow Specification

1. **Authentication Check & Login Submission**:
   - URL: `https://www.coinglass.com/login`
   - Email Selector: `page.get_by_role("textbox", name="Email")` -> `singhkaranbir0248@gmail.com`
   - Password Selector: `page.get_by_role("textbox", name="Password")` -> `Lu$er2hero`
   - Submit Button: `page.get_by_role("button", name="Login").nth(1)`

2. **S9 Layout Loading**:
   - URL: `https://www.coinglass.com/tv/layout/s9`
   - Login page is closed upon navigation to S9.

3. **L_1 Preset Activation**:
   - Layout menu button: `page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)`
   - Load Chart Layout menu item: `page.get_by_role("menuitem", name="Load Chart Layout")`
   - Preset button: `page.get_by_role("button", name="L_1")`

4. **15m Timeframe Enforcement (All 9 Cells)**:
   - Click cell canvas / frame to focus (`canvas.nth(1).click(position={"x": 280, "y": 90})`)
   - Click interval dropdown (`page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2)`)
   - Click `15m` button (`page.get_by_text("15m")`)

5. **Target Symbol Assignment (All 9 Cells)**:
   - Click cell canvas / frame (`canvas.nth(1).click(position={"x": 300, "y": 80})`)
   - Click symbol button (`page.get_by_role("button").first`)
   - Fill `#tv-ss` input with symbol (`locator("#tv-ss").fill(symbol)`)
   - Click matching result item or press `Enter`

### Affected Files
- [Engine_1.py](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/Engine_1.py)
- [coinglass_scraper.py](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/coinglass_scraper.py)
- [engine_components/coinglass_scraper.py](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/engine_components/coinglass_scraper.py)
- [tools/execute_perfect_coinglass_setup.py](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/tools/execute_perfect_coinglass_setup.py)

**Rule for all agents:** Do NOT edit button indices, dropdown locators, or navigation order in this sequence.

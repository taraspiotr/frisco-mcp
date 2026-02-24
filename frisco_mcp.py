"""
Frisco.pl MCP Server
Podłącz do Claude Desktop i rozmawiaj po polsku:
  "Kup mi zakupy na tydzień dla 2 osób"
  "Dodaj do koszyka: mleko 2l, chleb, masło"
  "Co mam w koszyku?"
"""

import json
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright

mcp = FastMCP("Frisco Shopping Agent")

# ── Globalna sesja przeglądarki (żeby nie logować za każdym razem) ──────────
_browser = None
_page = None
_logged_in = False


async def get_page():
    global _browser, _page
    if _page is None:
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=False)
        ctx = await _browser.new_context(locale="pl-PL")
        _page = await ctx.new_page()
    return _page


async def ensure_logged_in(email: str, password: str) -> bool:
    global _logged_in
    if _logged_in:
        return True

    page = await get_page()
    await page.goto("https://www.frisco.pl/login")
    await page.wait_for_load_state("networkidle")

    # Accept cookie consent
    try:
        await page.get_by_role("button", name="Akceptuję").click(timeout=3000)
        await page.wait_for_timeout(800)
    except Exception:
        pass

    # Close postcode popup
    try:
        await page.click("button.modal-new_close", timeout=2000)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    # Fill login form and submit
    try:
        await page.get_by_role("textbox", name="Adres e-mail").fill(email)
        await page.get_by_role("textbox", name="Hasło").fill(password)
        await page.get_by_role("button", name="Zaloguj").click()
        await page.wait_for_url(lambda url: "login" not in url, timeout=10000)
        _logged_in = True
        return True
    except Exception:
        return False


@mcp.tool()
async def add_items_to_cart(email: str, password: str, items: str) -> str:
    """
    Loguje się do Frisco.pl i dodaje produkty do koszyka.

    Parametry:
    - email: adres email konta Frisco
    - password: hasło do konta Frisco
    - items: lista produktów jako JSON string, np:
      '[{"name":"mleko","quantity":2,"search_query":"mleko"},{"name":"chleb","search_query":"chleb pszenny"}]'

    Przed wywołaniem tego narzędzia Claude powinien najpierw wygenerować listę
    produktów z opisu użytkownika i przedstawić ją do zatwierdzenia.

    WAŻNE: Agent NIE dokonuje płatności. Zatrzymuje się na etapie koszyka.
    """
    try:
        products = json.loads(items)
    except Exception:
        return '❌ Błąd: items musi być poprawnym JSON.\nPrzykład: \'[{"name":"mleko","quantity":2,"search_query":"mleko"}]\''

    logged = await ensure_logged_in(email, password)
    if not logged:
        return "❌ Nie udało się zalogować do Frisco.pl. Sprawdź email i hasło."

    page = await get_page()
    results = []

    for item in products:
        name = item.get("name", "?")
        query = item.get("search_query", name)
        qty = item.get("quantity", 1)

        try:
            # Search using the header search box (two-step: click header → type in expanded input)
            await page.get_by_role("textbox", name="Wyszukaj").click()
            search_input = page.get_by_role("textbox", name="Jakiego produktu szukasz?")
            await search_input.fill(query)
            await search_input.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            # Find first visible "Do koszyka" button on the search results page
            koszyk_btns = page.get_by_text("Do koszyka")
            count = await koszyk_btns.count()
            add_btn = None
            for i in range(count):
                btn = koszyk_btns.nth(i)
                if await btn.is_visible():
                    add_btn = btn
                    break

            if add_btn is None:
                results.append(f"⚠️  {name}: nie znaleziono")
                continue

            # Get product name from parent product-box_holder's link title
            found_name = await add_btn.evaluate("""el => {
                const box = el.closest('.product-box_holder');
                const link = box && box.querySelector('a[title]');
                return link ? link.title : '';
            }""") or name

            # Click qty times
            for _ in range(qty):
                await add_btn.click()
                await page.wait_for_timeout(500)

            results.append(f"✅ {found_name} x{qty}")

        except Exception as e:
            results.append(f"❌ {name}: {str(e)[:80]}")

    added = sum(1 for r in results if r.startswith("✅"))
    return f"""
🛒 Dodano {added}/{len(products)} produktów:

{chr(10).join(results)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Płatność realizujesz SAMODZIELNIE.
👉 https://www.frisco.pl/stn,cart
Przeglądarka jest otwarta — możesz od razu przejść do kasy.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


@mcp.tool()
async def view_cart(email: str, password: str) -> str:
    """Otwiera koszyk Frisco.pl i zwraca jego zawartość."""
    logged = await ensure_logged_in(email, password)
    if not logged:
        return "❌ Nie udało się zalogować."

    page = await get_page()
    await page.goto("https://www.frisco.pl/stn,cart")
    await page.wait_for_load_state("networkidle")

    try:
        items = await page.query_selector_all("[class*='CartItem'], [class*='cart-item']")
        total_el = await page.query_selector("[class*='Total'], [class*='total'], [class*='sum']")
        total = (await total_el.inner_text()).strip() if total_el else "?"
        if not items:
            return "🛒 Koszyk jest pusty."
        return f"🛒 {len(items)} produktów | Łącznie: {total}\n👉 https://www.frisco.pl/stn,cart"
    except Exception as e:
        return f"❌ Błąd: {e}"


@mcp.tool()
async def clear_session() -> str:
    """Zamyka sesję przeglądarki. Użyj gdy chcesz się wylogować lub zmienić konto."""
    global _browser, _page, _logged_in
    if _browser:
        await _browser.close()
    _browser = None
    _page = None
    _logged_in = False
    return "✅ Sesja zamknięta."


if __name__ == "__main__":
    mcp.run()

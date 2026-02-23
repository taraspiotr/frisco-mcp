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

    try:
        await page.click("button.cta:has-text('Akceptuję'), button[id*='accept'], button[class*='accept']", timeout=2000)
        await page.wait_for_timeout(800)
    except Exception:
        pass

    try:
        await page.click("button.modal-new_close", timeout=2000)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        await page.fill("input[type='email']", email)
        await page.fill("input[type='password']", password)
        await page.click("button[type='submit']")
        await page.wait_for_load_state("networkidle")
        if "login" not in page.url:
            _logged_in = True
            return True
        return False
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
            await page.goto(f"https://www.frisco.pl/search?q={query}&pg=1")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(800)

            product_cards = await page.query_selector_all(
                ".product-box, .mini-product-box"
            )

            if not product_cards:
                results.append(f"⚠️  {name}: nie znaleziono")
                continue

            card = product_cards[0]

            name_el = await card.query_selector("[class*='info-name'], h3")
            found_name = (await name_el.inner_text()).strip() if name_el else name

            price_el = await card.query_selector("[class*='normal-price'], [class*='price']")
            price = (await price_el.inner_text()).strip() if price_el else "?"

            add_btn = await card.query_selector(
                "[class*='cart-button'], button[class*='add'], button[class*='cart']"
            )
            if not add_btn:
                await card.hover()
                await page.wait_for_timeout(300)
                add_btn = await card.query_selector("button, [class*='cart']")

            if add_btn:
                await add_btn.click()
                await page.wait_for_timeout(600)
                results.append(f"✅ {found_name} ({price}) x{qty}")
            else:
                results.append(f"⚠️  {name}: znaleziono '{found_name}' ale brak przycisku Dodaj")

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

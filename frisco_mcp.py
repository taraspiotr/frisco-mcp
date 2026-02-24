"""
Frisco.pl MCP Server
Podłącz do Claude Desktop i rozmawiaj po polsku:
  "Kup mi zakupy na tydzień dla 2 osób"
  "Dodaj do koszyka: mleko 2l, chleb, masło"
  "Co mam w koszyku?"
"""

import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright

mcp = FastMCP("Frisco Shopping Agent")

# ── Globalna sesja przeglądarki (żeby nie logować za każdym razem) ──────────
_browser = None
_page = None
_logged_in = False

# ── Recipes storage ──────────────────────────────────────────────────────────
_RECIPES_PATH = Path.home() / ".frisco-mcp" / "recipes.json"


def _load_recipes() -> dict:
    if not _RECIPES_PATH.exists():
        return {"version": 1, "recipes": []}
    with open(_RECIPES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_recipes(data: dict) -> None:
    _RECIPES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RECIPES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Browser helpers ──────────────────────────────────────────────────────────

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
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1000)

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


async def _search_and_get_first_product(page, query: str) -> tuple[str, str | None]:
    """Search for query, return (found_name, add_button_locator_or_None)."""
    await page.get_by_role("textbox", name="Wyszukaj").click()
    search_input = page.get_by_role("textbox", name="Jakiego produktu szukasz?")
    await search_input.fill(query)
    await search_input.press("Enter")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    koszyk_btns = page.get_by_text("Do koszyka")
    count = await koszyk_btns.count()
    for i in range(count):
        btn = koszyk_btns.nth(i)
        if await btn.is_visible():
            found_name = await btn.evaluate("""el => {
                const box = el.closest('.product-box_holder');
                const link = box && box.querySelector('a[title]');
                return link ? link.title : '';
            }""") or query
            return found_name, btn

    return query, None


# ── Recipe tools (no browser) ────────────────────────────────────────────────

@mcp.tool()
def save_recipe(name: str, servings: int, ingredients: str, notes: str = "") -> str:
    """
    Zapisuje przepis kulinarny do lokalnego pliku.

    Parametry:
    - name: nazwa przepisu
    - servings: liczba porcji
    - ingredients: lista składników jako JSON string, np:
      '[{"name":"Makaron","quantity":400,"unit":"g","search_query":"makaron spaghetti"}]'
      Pola: name (wymagane), quantity (wymagane), unit (wymagane), search_query (opcjonalne)
    - notes: opcjonalne notatki

    Jeśli przepis o tej samej nazwie już istnieje, zostanie nadpisany.
    """
    try:
        ing_list = json.loads(ingredients)
    except Exception:
        return "❌ Błąd: ingredients musi być poprawnym JSON."

    data = _load_recipes()
    now = datetime.now().isoformat(timespec="seconds")

    existing = next(
        (r for r in data["recipes"] if r["name"].lower() == name.lower()), None
    )
    if existing:
        existing["name"] = name
        existing["servings"] = servings
        existing["notes"] = notes
        existing["ingredients"] = ing_list
        existing["updated_at"] = now
        recipe_id = existing["id"]
        action = "zaktualizowano"
    else:
        recipe_id = str(uuid.uuid4())
        data["recipes"].append({
            "id": recipe_id,
            "name": name,
            "servings": servings,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
            "ingredients": ing_list,
        })
        action = "zapisano"

    _save_recipes(data)
    return (
        f"✅ Przepis '{name}' {action}.\n"
        f"ID: {recipe_id}\n"
        f"Składniki: {len(ing_list)}\n"
        f"Porcje: {servings}"
    )


@mcp.tool()
def list_recipes() -> str:
    """Zwraca listę wszystkich zapisanych przepisów."""
    data = _load_recipes()
    recipes = data.get("recipes", [])
    if not recipes:
        return "Brak zapisanych przepisów."

    lines = ["📋 Zapisane przepisy:\n"]
    for r in recipes:
        ing_count = len(r.get("ingredients", []))
        lines.append(
            f"• {r['name']} — {r['servings']} porcji, {ing_count} składników"
        )
    return "\n".join(lines)


@mcp.tool()
def delete_recipe(name: str) -> str:
    """
    Usuwa przepis o podanej nazwie (bez rozróżniania wielkości liter).

    Parametry:
    - name: nazwa przepisu do usunięcia
    """
    data = _load_recipes()
    original_count = len(data["recipes"])
    data["recipes"] = [
        r for r in data["recipes"] if r["name"].lower() != name.lower()
    ]

    if len(data["recipes"]) == original_count:
        available = ", ".join(r["name"] for r in data["recipes"]) or "brak"
        return f"❌ Nie znaleziono przepisu '{name}'.\nDostępne: {available}"

    _save_recipes(data)
    return f"✅ Przepis '{name}' usunięty."


# ── Cart tools ───────────────────────────────────────────────────────────────

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
            found_name, add_btn = await _search_and_get_first_product(page, query)

            if add_btn is None:
                results.append(f"⚠️  {name}: nie znaleziono")
                continue

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
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    try:
        result = await page.evaluate("""() => {
            const boxes = Array.from(document.querySelectorAll('.product-box_holder'))
                .filter(el => el.offsetParent !== null);

            const items = boxes.map(box => {
                const nameEl = box.querySelector('a[title]');
                const name = nameEl ? nameEl.title : '?';

                const priceEl = box.querySelector('[class*="price"], [class*="Price"]');
                const price = priceEl ? priceEl.innerText.trim().replace(/\\s+/g, ' ') : '';

                const qtyEl = box.querySelector('input[type="number"], [class*="stepper"], [class*="quantity"]');
                const qty = qtyEl ? (qtyEl.value || qtyEl.innerText || '1').trim() : '1';

                return { name, price, qty };
            });

            const totalEl = document.querySelector(
                '[class*="summary"] [class*="price"], [class*="checkout"] [class*="total"], ' +
                '[class*="Summary"] [class*="Price"], [class*="CartSummary"]'
            );
            const total = totalEl ? totalEl.innerText.trim().replace(/\\s+/g, ' ') : null;

            return { items, total };
        }""")

        items = result.get("items", [])
        total = result.get("total")

        if not items:
            return "🛒 Koszyk jest pusty (lub nie udało się odczytać zawartości).\n👉 https://www.frisco.pl/stn,cart"

        lines = ["🛒 Zawartość koszyka:\n"]
        for it in items:
            qty = it.get("qty", "1")
            price = it.get("price", "")
            price_part = f" — {price}" if price else ""
            lines.append(f"- {it['name']} x{qty}{price_part}")

        if total:
            lines.append(f"\n💰 Łącznie: {total}")

        lines.append("\n👉 https://www.frisco.pl/stn,cart")
        return "\n".join(lines)

    except Exception as e:
        return f"❌ Błąd odczytu koszyka: {e}"


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


# ── Product info tools ───────────────────────────────────────────────────────

@mcp.tool()
async def search_products(email: str, password: str, query: str, top_n: int = 5) -> str:
    """
    Wyszukuje produkty na Frisco.pl i zwraca listę z nazwami i cenami.
    Przydatne do porównywania produktów i wyboru zdrowych opcji.

    Parametry:
    - email, password: dane logowania
    - query: fraza wyszukiwania (np. "jogurt naturalny")
    - top_n: ile produktów zwrócić (domyślnie 5)
    """
    logged = await ensure_logged_in(email, password)
    if not logged:
        return "❌ Nie udało się zalogować."

    page = await get_page()
    encoded_query = query.replace(" ", "+")
    await page.goto(f"https://www.frisco.pl/q,{encoded_query}/stn,searchResults")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    try:
        products = await page.evaluate(f"""() => {{
            const boxes = Array.from(document.querySelectorAll('.product-box_holder'))
                .filter(el => el.offsetParent !== null)
                .slice(0, {top_n});

            return boxes.map(box => {{
                const nameEl = box.querySelector('a[title]');
                const name = nameEl ? nameEl.title : '?';

                const priceEl = box.querySelector('[class*="price"], [class*="Price"]');
                const price = priceEl ? priceEl.innerText.trim().replace(/\\s+/g, ' ') : '';

                return {{ name, price }};
            }});
        }}""")

        if not products:
            return f"❌ Nie znaleziono produktów dla: '{query}'"

        lines = [f"🔍 Wyniki dla '{query}':\n"]
        for i, p in enumerate(products, 1):
            price_part = f" | {p['price']}" if p.get("price") else ""
            lines.append(f"{i}. {p['name']}{price_part}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Błąd wyszukiwania: {e}"


@mcp.tool()
async def get_product_info(email: str, password: str, query: str) -> str:
    """
    Wyszukuje produkt i zwraca szczegółowe informacje: makroskładniki i listę składników.
    Przydatne do oceny wartości odżywczych produktu.

    Parametry:
    - email, password: dane logowania
    - query: fraza wyszukiwania (np. "masło ekstra")
    """
    logged = await ensure_logged_in(email, password)
    if not logged:
        return "❌ Nie udało się zalogować."

    page = await get_page()
    encoded_query = query.replace(" ", "+")
    await page.goto(f"https://www.frisco.pl/q,{encoded_query}/stn,searchResults")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    # Find first visible product link
    try:
        product_links = page.locator("a[href*='/pid,'][title]")
        count = await product_links.count()
        product_url = None
        for i in range(count):
            link = product_links.nth(i)
            if await link.is_visible():
                product_url = await link.get_attribute("href")
                break

        if not product_url:
            return f"❌ Nie znaleziono produktu dla: '{query}'"

        if not product_url.startswith("http"):
            product_url = "https://www.frisco.pl" + product_url

        await page.goto(product_url)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

    except Exception as e:
        return f"❌ Błąd nawigacji do produktu: {e}"

    try:
        info = await page.evaluate(r"""() => {
            // Product name
            const h1 = document.querySelector('h1');
            const name = h1 ? h1.innerText.trim() : '?';

            // Price
            const priceEl = document.querySelector('[class*="price"], [class*="Price"]');
            const price = priceEl ? priceEl.innerText.trim().replace(/\s+/g, ' ') : '';

            // Full page text for parsing
            const bodyText = document.body.innerText;

            // Ingredients: text after "Skład:"
            const skladMatch = bodyText.match(/Sk[łl]ad\s*[:：]\s*([^\n]{10,})/i);
            const ingredients = skladMatch ? skladMatch[1].trim() : null;

            // Macros: walk table rows and definition lists
            const macros = {};
            const keyMap = {
                'kcal': 'kcal',
                'energia': 'kcal',
                'białko': 'białko',
                'bialko': 'białko',
                'tłuszcz': 'tłuszcz',
                'tluszcz': 'tłuszcz',
                'węglowodan': 'węglowodany',
                'weglowodan': 'węglowodany',
                'cukr': 'cukry',
                'błonnik': 'błonnik',
                'blonnik': 'błonnik',
                'sól': 'sól',
                'sol': 'sól',
            };

            function extractMacro(label, value) {
                const lc = label.toLowerCase();
                for (const [key, canonical] of Object.entries(keyMap)) {
                    if (lc.includes(key) && !macros[canonical]) {
                        macros[canonical] = value.trim().replace(/\s+/g, ' ');
                        break;
                    }
                }
            }

            // Try <tr> rows
            document.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td, th');
                if (cells.length >= 2) {
                    extractMacro(cells[0].innerText, cells[1].innerText);
                }
            });

            // Try <dt>/<dd> pairs
            document.querySelectorAll('dt').forEach(dt => {
                const dd = dt.nextElementSibling;
                if (dd && dd.tagName === 'DD') {
                    extractMacro(dt.innerText, dd.innerText);
                }
            });

            // Fallback: regex on body text
            if (!macros['kcal']) {
                const m = bodyText.match(/(\d+[\s,]\d*)\s*kcal/i);
                if (m) macros['kcal'] = m[1] + ' kcal';
            }

            return { name, price, ingredients, macros };
        }""")

        name = info.get("name", "?")
        price = info.get("price", "")
        ingredients = info.get("ingredients")
        macros = info.get("macros", {})

        lines = [f"🛍️ {name}"]
        if price:
            lines.append(f"💰 Cena: {price}")

        lines.append("")
        if macros:
            lines.append("📊 Wartości odżywcze (na 100g):")
            macro_order = ["kcal", "białko", "tłuszcz", "węglowodany", "cukry", "błonnik", "sól"]
            for key in macro_order:
                if key in macros:
                    lines.append(f"  {key}: {macros[key]}")
            for key, val in macros.items():
                if key not in macro_order:
                    lines.append(f"  {key}: {val}")
        else:
            lines.append("📊 Brak danych o wartościach odżywczych.")

        lines.append("")
        if ingredients:
            lines.append(f"🧪 Skład: {ingredients}")
        else:
            lines.append("🧪 Brak informacji o składzie.")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Błąd odczytu informacji o produkcie: {e}"


# ── Recipe cart tool ─────────────────────────────────────────────────────────

@mcp.tool()
async def add_recipe_to_cart(
    email: str, password: str, recipe_name: str, servings: int = 0
) -> str:
    """
    Wyszukuje przepis i dodaje wszystkie składniki do koszyka Frisco.pl.
    Automatycznie przelicza ilości na odpowiednią liczbę porcji.

    Parametry:
    - email, password: dane logowania
    - recipe_name: nazwa przepisu (bez rozróżniania wielkości liter)
    - servings: liczba porcji (0 = użyj domyślnej liczby z przepisu)

    WAŻNE: Agent NIE dokonuje płatności. Zatrzymuje się na etapie koszyka.
    """
    data = _load_recipes()
    recipe = next(
        (r for r in data["recipes"] if r["name"].lower() == recipe_name.lower()), None
    )
    if not recipe:
        available = ", ".join(r["name"] for r in data["recipes"]) or "brak"
        return f"❌ Nie znaleziono przepisu '{recipe_name}'.\nDostępne przepisy: {available}"

    logged = await ensure_logged_in(email, password)
    if not logged:
        return "❌ Nie udało się zalogować do Frisco.pl. Sprawdź email i hasło."

    base_servings = recipe["servings"]
    desired_servings = servings if servings > 0 else base_servings
    scale = desired_servings / base_servings if base_servings > 0 else 1.0

    page = await get_page()
    results = []

    # Regex patterns for parsing package sizes from product names
    size_patterns = [
        (r"(\d+(?:[,.]?\d+)?)\s*kg", "kg", 1000),   # kg → grams
        (r"(\d+(?:[,.]?\d+)?)\s*l\b", "l", 1000),    # liters → ml
        (r"(\d+)\s*g\b", "g", 1),                     # grams
        (r"(\d+)\s*ml\b", "ml", 1),                   # milliliters
        (r"(\d+)\s*szt\b", "szt", 1),                 # pieces
    ]

    unit_to_base = {
        "g": "g", "kg": "g",
        "ml": "ml", "l": "ml",
        "szt": "szt",
    }

    def parse_package_size(product_name: str, needed_unit: str) -> float | None:
        """Return package size in same unit as needed_unit, or None if can't parse."""
        target_base = unit_to_base.get(needed_unit.lower())
        if not target_base:
            return None

        for pattern, unit, multiplier in size_patterns:
            m = re.search(pattern, product_name, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", ".")) * multiplier
                found_base = unit_to_base.get(unit)
                if found_base == target_base:
                    # Convert back to needed_unit
                    if needed_unit.lower() in ("kg",):
                        return val / 1000
                    if needed_unit.lower() in ("l",):
                        return val / 1000
                    return val
        return None

    for ing in recipe.get("ingredients", []):
        ing_name = ing.get("name", "?")
        query = ing.get("search_query", ing_name)
        base_qty = float(ing.get("quantity", 1))
        unit = ing.get("unit", "szt")
        needed_qty = base_qty * scale

        try:
            found_name, add_btn = await _search_and_get_first_product(page, query)

            if add_btn is None:
                results.append(f"⚠️  {ing_name}: nie znaleziono produktu")
                continue

            pkg_size = parse_package_size(found_name, unit)

            if pkg_size and pkg_size > 0:
                packages = math.ceil(needed_qty / pkg_size)
                bought_qty = packages * pkg_size
                excess = bought_qty - needed_qty
                excess_str = f" (nadmiar: {excess:.0f} {unit})" if excess > 0 else ""
                summary = (
                    f"potrzeba {needed_qty:.0f}{unit} → "
                    f"znaleziono {pkg_size:.0f}{unit}/opak → "
                    f"dodano {packages} szt{excess_str}"
                )
            else:
                packages = 1
                summary = f"potrzeba {needed_qty:.0f}{unit} → dodano 1 szt. (nie rozpoznano rozmiaru opakowania)"

            for _ in range(packages):
                await add_btn.click()
                await page.wait_for_timeout(500)

            results.append(f"✅ {ing_name}: {summary}\n   → {found_name}")

        except Exception as e:
            results.append(f"❌ {ing_name}: {str(e)[:80]}")

    added = sum(1 for r in results if r.startswith("✅"))
    scale_info = (
        f"Przepis na {desired_servings} porcji"
        if desired_servings != base_servings
        else f"Przepis na {base_servings} porcji (domyślnie)"
    )

    return f"""
🍳 Przepis: {recipe['name']}
📐 {scale_info} | Dodano {added}/{len(recipe.get('ingredients', []))} składników:

{chr(10).join(results)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Płatność realizujesz SAMODZIELNIE.
👉 https://www.frisco.pl/stn,cart
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


if __name__ == "__main__":
    mcp.run()

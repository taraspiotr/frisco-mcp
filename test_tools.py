"""
Manual test script for frisco_mcp tools.

Credentials are loaded from ~/.frisco-mcp/credentials.json:
  { "email": "you@example.com", "password": "secret" }

Falls back to CLI args or interactive prompt if file is missing/empty.
"""

import asyncio
import sys
import json
from pathlib import Path

_CREDS_PATH = Path.home() / ".frisco-mcp" / "credentials.json"

def _load_credentials() -> tuple[str, str]:
    if _CREDS_PATH.exists():
        try:
            c = json.loads(_CREDS_PATH.read_text())
            e, p = c.get("email", ""), c.get("password", "")
            if e and p:
                print(f"Loaded credentials from {_CREDS_PATH} ({e})")
                return e, p
        except Exception:
            pass
    # Fallback: CLI args or prompt
    e = sys.argv[1] if len(sys.argv) > 1 else input("Email: ")
    p = sys.argv[2] if len(sys.argv) > 2 else input("Password: ")
    return e, p

email, password = _load_credentials()
sys.argv = sys.argv[:1]  # strip args before importing FastMCP

from frisco_mcp import (
    save_recipe, list_recipes, delete_recipe,
    add_recipe_to_cart, search_products, get_product_info,
    view_cart, _load_recipes,
)


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def show(label: str, result):
    print(f"\n[{label}]\n{result}")


# ── 1. Recipe tools (no browser) ────────────────────────────────────────────

section("1. save_recipe")
r = save_recipe(
    name="Spaghetti bolognese",
    servings=4,
    ingredients=json.dumps([
        {"name": "Makaron spaghetti", "quantity": 400, "unit": "g", "search_query": "makaron spaghetti"},
        {"name": "Mielona wołowina",  "quantity": 500, "unit": "g", "search_query": "mielona wołowina"},
        {"name": "Passata pomidorowa","quantity": 500, "unit": "g", "search_query": "passata pomidorowa"},
        {"name": "Cebula",            "quantity": 1,   "unit": "szt","search_query": "cebula"},
    ]),
    notes="Klasyczny włoski przepis",
)
show("save_recipe", r)

section("2. list_recipes")
show("list_recipes", list_recipes())

section("3. save_recipe (overwrite)")
r2 = save_recipe(
    name="Spaghetti bolognese",
    servings=2,
    ingredients=json.dumps([
        {"name": "Makaron spaghetti", "quantity": 200, "unit": "g"},
        {"name": "Mielona wołowina",  "quantity": 250, "unit": "g"},
    ]),
)
show("save_recipe (overwrite)", r2)

section("4. list_recipes after overwrite")
show("list_recipes", list_recipes())

section("5. delete_recipe (nonexistent)")
show("delete (nonexistent)", delete_recipe("Nie ma takiego"))

section("6. Verify JSON file")
data = _load_recipes()
recipe = next((r for r in data["recipes"] if r["name"] == "Spaghetti bolognese"), None)
print(f"Recipe in file: {json.dumps(recipe, ensure_ascii=False, indent=2)}")

input("\n✅ Recipe tests done. Press Enter to start BROWSER tests (Chromium will open)...")

# ── 2. Browser tools ─────────────────────────────────────────────────────────

async def run_browser_tests():
    section("7. search_products — 'jogurt naturalny' top_n=3")
    r = await search_products(email, password, "jogurt naturalny", top_n=3)
    show("search_products", r)

    section("8. get_product_info — 'masło ekstra'")
    r = await get_product_info(email, password, "masło ekstra")
    show("get_product_info", r)

    section("9. add_recipe_to_cart — 'Spaghetti bolognese' servings=2")
    r = await add_recipe_to_cart(email, password, "Spaghetti bolognese", servings=2)
    show("add_recipe_to_cart", r)

    section("10. view_cart")
    r = await view_cart(email, password)
    show("view_cart", r)

    # Cleanup
    section("11. delete_recipe")
    show("delete_recipe", delete_recipe("Spaghetti bolognese"))
    show("list after delete", list_recipes())

    print("\n\n✅ All tests complete.")

asyncio.run(run_browser_tests())

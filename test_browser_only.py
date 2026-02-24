"""Browser-only test: search_products, get_product_info, view_cart."""
import asyncio, json, sys
from pathlib import Path

sys.argv = sys.argv[:1]
creds = json.loads((Path.home() / ".frisco-mcp/credentials.json").read_text())
email, password = creds["email"], creds["password"]
print(f"Using account: {email}\n")

from frisco_mcp import search_products, get_product_info, view_cart


def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


async def main():
    section("search_products — 'jogurt naturalny' top_n=3")
    r = await search_products(email, password, "jogurt naturalny", top_n=3)
    print(r)

    section("get_product_info — 'masło ekstra'")
    r = await get_product_info(email, password, "masło ekstra")
    print(r)

    section("view_cart")
    r = await view_cart(email, password)
    print(r)

    print("\n✅ Done.")

asyncio.run(main())

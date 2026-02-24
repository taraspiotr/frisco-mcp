# frisco-mcp

MCP server for [Frisco.pl](https://www.frisco.pl) — lets Claude add groceries to your cart, search products, get nutritional info, and manage recipes, all via natural language.

## Features

- **Add items to cart** — describe what you need, Claude finds and adds them
- **View cart** — read current cart contents and total
- **Search products** — browse top results with prices for comparison
- **Product nutritional info** — macros (kcal, protein, fat, carbs) + ingredient list
- **Recipe storage** — save, list, delete recipes locally
- **Add recipe to cart** — automatically scale quantities and add all ingredients

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Playwright (Chromium)
- A Frisco.pl account

## Installation

```bash
git clone https://github.com/tarasiewicz/frisco-mcp.git
cd frisco-mcp
uv sync          # or: pip install mcp playwright
playwright install chromium
```

## Configuration

### Credentials

Create `~/.frisco-mcp/credentials.json`:

```json
{
  "email": "you@example.com",
  "password": "yourpassword"
}
```

This file is outside the repo and never committed.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "frisco": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/frisco-mcp", "python", "frisco_mcp.py"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `add_items_to_cart` | Search and add a list of products to cart |
| `view_cart` | Read current cart contents and total |
| `search_products` | Return top N results for a query (name + price) |
| `get_product_info` | Full macros + ingredient list for a product |
| `save_recipe` | Save a recipe with ingredients to local storage |
| `list_recipes` | List all saved recipes |
| `delete_recipe` | Delete a recipe by name |
| `add_recipe_to_cart` | Add all recipe ingredients to cart, optionally scaled |
| `clear_session` | Close browser session / switch account |

## Example prompts (Polish)

```
Dodaj do koszyka: mleko 2l, chleb pszenny, masło ekstra
Jakie jogurty naturalne są dostępne? Pokaż 5 najtańszych
Jakie ma makroskładniki masło ekstra?
Zapisz przepis na spaghetti bolognese na 4 porcje
Dodaj składniki przepisu "spaghetti bolognese" do koszyka na 2 porcje
Co mam w koszyku?
```

## Notes

- The agent **never makes payments** — it stops at the cart stage
- A Chromium browser window opens visibly (non-headless) so you can monitor actions
- Recipes are stored in `~/.frisco-mcp/recipes.json`

## License

MIT

# 🛒 Frisco MCP — setup pod uv

## Krok 1 — skopiuj projekt

Skopiuj folder `frisco-mcp` gdzieś na dysku, np. do `~/frisco-mcp`.

```
~/frisco-mcp/
├── frisco_mcp.py
├── pyproject.toml
└── SETUP.md
```

---

## Krok 2 — utwórz venv i zainstaluj zależności

```bash
cd ~/frisco-mcp

uv venv claude
uv pip install -r pyproject.toml   # lub:
uv pip install "mcp[cli]" playwright

# Zainstaluj przeglądarkę Chromium (tylko raz!)
uv run playwright install chromium
```

---

## Krok 3 — sprawdź ścieżkę do Pythona w venv

```bash
# Na Macu po uv venv claude będzie w:
ls ~/frisco-mcp/claude/bin/python
# → ~/frisco-mcp/claude/bin/python
```

---

## Krok 4 — dodaj do Claude Desktop

Otwórz **Claude Desktop** → górne menu **Claude** → **Settings** → zakładka **Developer** → **Edit Config**

Wklej (podmień `TWOJE_IMIE`):

```json
{
  "mcpServers": {
    "frisco": {
      "command": "/Users/TWOJE_IMIE/frisco-mcp/claude/bin/python",
      "args": ["/Users/TWOJE_IMIE/frisco-mcp/frisco_mcp.py"]
    }
  }
}
```

> **Tip:** zamiast `TWOJE_IMIE` wklej wynik polecenia `echo $HOME` z terminala.

---

## Krok 5 — restart Claude Desktop

Zamknij i otwórz ponownie Claude. W oknie czatu pojawi się **ikonka 🔨** — serwer działa.

---

## Krok 6 — użyj!

Napisz do Claude:

```
Zrób mi zakupy na tydzień dla 2 osób — śniadania i obiady.
email: jan@gmail.com, hasło: mojhaslo
```

Claude:
1. Wygeneruje listę produktów i pokaże do zatwierdzenia
2. Otworzy Chromium, zaloguje się na Frisco
3. Doda produkty do koszyka
4. **Zatrzyma się przy kasie** — resztę (termin, płatność) robisz Ty

---

## Inne przydatne komendy

```
"Co mam w koszyku na Frisco? email: ..., hasło: ..."

"Zamknij sesję Frisco"  (wylogowuje, zamyka przeglądarkę)
```

---

## Troubleshooting

**Brak ikonki 🔨 w Claude Desktop**
→ Sprawdź czy ścieżki w JSON są absolutne i poprawne
→ Zrestartuj Claude (Cmd+Q, nie tylko zamknij okno)
→ Sprawdź logi: `~/Library/Logs/Claude/mcp-server-frisco.log`

**Błąd logowania**
→ Frisco może pokazać CAPTCHA przy pierwszym logowaniu automatycznym
→ Przeglądarka jest widoczna (`headless=False`) — możesz ją kliknąć ręcznie
→ Przetestuj ręcznie: `cd ~/frisco-mcp && uv run python frisco_mcp.py`

**"command not found: uv"**
→ Użyj pełnej ścieżki w JSON: `"command": "/Users/TWOJE_IMIE/frisco-mcp/claude/bin/python"`
   (właśnie dlatego rekomendujemy bezpośrednią ścieżkę do Pythona z venv)

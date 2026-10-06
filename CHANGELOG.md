# Changelog

## 5.5.0 / shell 19.2 — 2026-10-06

- Kanonicky zdroj DB jsou modulove JSON, ne zastaraly database_full.json
- Aliasy (CS/EN) a /aliases; /search je umi rozbalit
- Odvozene vazby: drops, rewards, found_in, used_in (pack se nemeni)
- User vrstva v user_layer.db (/user/favorites, inventar, buildy) — rebuild packu ji nemaze
- modules/ohg_user.js + validate_pack.py
- Pack porad 372 entit

## 5.4.0 / shell 19.1 — 2026-10-01

- /ui servuje shell i staticke assety
- SQLite: indexy, katalog entities, FTS5, odvozene links
- API: /health, /integrity, /search, /links

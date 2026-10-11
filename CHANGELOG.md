# Changelog

## 5.5.0 / shell 19.2 — 2026-10-11

- Databáze: `data_issues` audit (chybějící/duplicitní id, prázdná jména, nerozpoznané ingredience), indexy type/rarity, FTS s odstraněním diakritiky, více vazeb (drops, located_at)
- API: verze z version.json, bezpečnější FTS query
- Pack 372 entit beze změny obsahu. User layer odděleně.

## 5.4.0 / shell 19.1 — 2026-10-01

- `/ui` servíruje shell i statické assety (`/modules`, `ohg_data.js`, `ohg_sw.js`) — SPA se na API opravdu spustí
- SQLite: indexy, katalog `entities`, FTS5, odvozené `links` (recept → materiál/rostlina)
- API: `/health`, `/integrity`, `/search` (FTS), `/links/{table}/{id}`, stránkování
- `db_build.py`; updater ho preferuje před starým schématem
- Badge v hostu v19; pack 372 beze změny

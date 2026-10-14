# Changelog

## 5.5.0 / shell 19.2 — 2026-10-14

- Dockerfile for one-command API container (python db_build + uvicorn)
- db_build.py: extra indexes on type and rarity columns where present
- Data: placeholders for upcoming SOCR – Cosmic Visitor (Frost Vortex weapon) and Snowline Elite Vest
- Records bumped to 374

## 5.4.0 / shell 19.1 — 2026-10-01

- `/ui` servíruje shell i statické assety (`/modules`, `ohg_data.js`, `ohg_sw.js`) — SPA se na API opravdu spustí
- SQLite: indexy, katalog `entities`, FTS5, odvozené `links` (recept → materiál/rostlina)
- API: `/health`, `/integrity`, `/search` (FTS), `/links/{table}/{id}`, stránkování
- `db_build.py`; updater ho preferuje před starým schématem
- Badge v hostu v19; pack 372 beze změny

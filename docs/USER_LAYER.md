# User layer 5.8

Pack (`once_human.db`) a user data (`once_human_user.db`) jsou oddělené.

- `python db_build.py` maže jen pack DB.
- Favorites, notes, builds a queue jdou přes `user_store.py`.
- Export/import: `export_user()` / `import_user()`.
- API: `/user`, `/user/export`, `/user/import`, `/user/favorites/{table}/{id}`.
- `/update/run` jen z 127.0.0.1. Uvicorn defaultně binduje localhost.
- Počet entit v packu zůstává 372.

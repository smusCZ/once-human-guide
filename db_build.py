#!/usr/bin/env python3
"""Build once_human.db from module JSON or database_full.json.

Improved for v5.5:
- Schema 5.5 with extra JSON column, data_issues, better indexes
- FTS5 with unicode61 remove_diacritics=2 for Czech
- More links (ingredients, located_at)
- Version from version.json
- Validation issues logged (does not modify pack)
User-layer data is never written here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"

MODULES = {
    "deviations": "deviations.json",
    "weapons": "weapons.json",
    "armor": "armor.json",
    "mods": "mods.json",
    "bosses": "bosses.json",
    "locations": "map_locations.json",
    "recipes": "recipes.json",
    "materials": "materials.json",
    "scenarios": "scenarios.json",
    "quests": "quests.json",
    "events": "events.json",
    "creatures": "creatures.json",
    "npcs": "npcs.json",
    "plants": "plants.json",
    "fish": "fish.json",
    "animals": "animals.json",
    "flowers": "flowers.json",
}

CORE_COLS = {
    "deviations": ["id", "name", "type", "rarity", "utility", "desc", "mood", "source", "tags"],
    "weapons": ["id", "name", "type", "rarity", "style", "desc", "tags"],
    "armor": ["id", "name", "type", "rarity", "style", "pieces", "desc", "tags"],
    "mods": ["id", "name", "type", "rarity", "slot", "desc", "source", "tags"],
    "bosses": ["id", "name", "region", "location", "desc", "drops"],
    "locations": ["id", "name", "type", "region", "x", "y", "desc"],
    "recipes": ["id", "name", "type", "station", "ingredients", "effect", "desc"],
    "materials": ["id", "name", "type", "desc"],
    "scenarios": ["id", "name", "type", "phase", "desc", "rewards", "locations", "tags"],
    "quests": ["id", "name", "type", "region", "desc", "rewards", "tags"],
    "events": ["id", "name", "type", "status", "desc", "rewards", "location", "timer", "tags"],
    "creatures": ["id", "name", "type", "threat", "desc", "location", "tags"],
    "npcs": ["id", "name", "type", "location", "desc", "tags"],
    "plants": ["id", "name", "type", "desc", "uses", "tags"],
    "fish": ["id", "name", "type", "desc", "location", "tags"],
    "animals": ["id", "name", "type", "desc", "drops", "location", "taming", "tags"],
    "flowers": ["id", "name", "type", "desc", "tags"],
}

def _load_modules() -> dict:
    data = {}
    for table, filename in MODULES.items():
        path = BASE / filename
        if not path.exists():
            data[table] = []
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        data[table] = raw if isinstance(raw, list) else raw.get(table, [])
    return data

def load_pack() -> dict:
    full = BASE / "database_full.json"
    if full.exists():
        data = json.loads(full.read_text(encoding="utf-8"))
        if isinstance(data, dict) and any(k in data for k in MODULES):
            return data
    data = _load_modules()
    ver_path = BASE / "version.json"
    version = "local"
    if ver_path.exists():
        version = json.loads(ver_path.read_text(encoding="utf-8")).get("data_version", version)
    data["version"] = version
    return data

def _blob(row: dict) -> str:
    parts = []
    for key, value in row.items():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts)

def _norm(name: str) -> str:
    return " ".join((name or "").lower().replace("-", " ").split())

def build(db_path: Path | None = None) -> dict:
    data = load_pack()
    path = db_path or DB_PATH
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    ver = data.get("version", "unknown")
    now = datetime.now(timezone.utc).isoformat()
    c.execute("CREATE TABLE data_versions (table_name TEXT PRIMARY KEY, version TEXT, updated_at TEXT)")
    c.execute("INSERT INTO data_versions VALUES ('all', ?, ?)", (ver, now))
    c.execute("""CREATE TABLE entities (
        table_name TEXT NOT NULL, id TEXT NOT NULL, name TEXT,
        kind TEXT, rarity TEXT, region TEXT, blob TEXT, extra TEXT,
        PRIMARY KEY (table_name, id)
    )""")
    c.execute("""CREATE TABLE links (
        src_table TEXT, src_id TEXT, dst_table TEXT, dst_id TEXT,
        relation TEXT, score REAL,
        PRIMARY KEY (src_table, src_id, dst_table, dst_id, relation)
    )""")
    c.execute("""CREATE TABLE data_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT, item_id TEXT, issue TEXT, detail TEXT
    )""")
    total = 0
    catalog = []
    seen_ids = defaultdict(set)
    for table, core in CORE_COLS.items():
        schema_parts = []
        for col in core:
            typ = "REAL" if col in ("x", "y") else "TEXT"
            pk = " PRIMARY KEY" if col == "id" else ""
            schema_parts.append(f"{col} {typ}{pk}")
        schema_parts.append("extra TEXT")
        schema = ", ".join(schema_parts)
        c.execute(f"CREATE TABLE {table} ({schema})")
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_name ON {table}(name)")
        if "type" in core:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_type ON {table}(type)")
        if "rarity" in core:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_rarity ON {table}(rarity)")
        if "region" in core:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_region ON {table}(region)")
        for row in data.get(table, []):
            item_id = row.get("id")
            name = row.get("name") or ""
            if not item_id:
                c.execute("INSERT INTO data_issues (table_name, item_id, issue, detail) VALUES (?,?,?,?)",
                          (table, None, "missing_id", json.dumps(row, ensure_ascii=False)[:200]))
                continue
            if item_id in seen_ids[table]:
                c.execute("INSERT INTO data_issues (table_name, item_id, issue, detail) VALUES (?,?,?,?)",
                          (table, item_id, "duplicate_id", ""))
            seen_ids[table].add(item_id)
            if not name.strip():
                c.execute("INSERT INTO data_issues (table_name, item_id, issue, detail) VALUES (?,?,?,?)",
                          (table, item_id, "empty_name", ""))
            vals = []
            extra = {}
            for col in core:
                value = row.get(col)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                vals.append(value)
            for k, v in row.items():
                if k not in core and v is not None:
                    extra[k] = v
            vals.append(json.dumps(extra, ensure_ascii=False) if extra else None)
            placeholders = ",".join("?" * len(vals))
            c.execute(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", vals)
            catalog.append((table, row))
            total += 1
    by_name = {}
    for table, row in catalog:
        name = row.get("name") or ""
        extra_blob = json.dumps({k: v for k, v in row.items() if k not in CORE_COLS.get(table, [])}, ensure_ascii=False)
        c.execute("INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?)",
                  (table, row.get("id"), name, row.get("type") or row.get("utility") or "",
                   row.get("rarity") or "", row.get("region") or row.get("location") or "",
                   _blob(row), extra_blob))
        key = _norm(name)
        if key:
            by_name.setdefault(key, []).append((table, row.get("id")))
    link_count = 0
    for row in data.get("recipes", []):
        ingredients = row.get("ingredients") or []
        if isinstance(ingredients, str):
            try:
                ingredients = json.loads(ingredients)
            except json.JSONDecodeError:
                ingredients = []
        for ing in ingredients:
            label = ing.get("name") if isinstance(ing, dict) else str(ing)
            hit = by_name.get(_norm(label))
            if not hit:
                c.execute("INSERT INTO data_issues (table_name, item_id, issue, detail) VALUES (?,?,?,?)",
                          ("recipes", row.get("id"), "unresolved_ingredient", label))
                continue
            for dst_table, dst_id in hit:
                if dst_table == "recipes":
                    continue
                c.execute("INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
                          ("recipes", row.get("id"), dst_table, dst_id, "ingredient", 1.0))
                link_count += 1
    for src_table in ("bosses", "creatures", "npcs", "fish", "animals"):
        for row in data.get(src_table, []):
            loc_name = row.get("location") or ""
            if not loc_name:
                continue
            hit = by_name.get(_norm(loc_name))
            if hit:
                for dst_table, dst_id in hit:
                    if dst_table == "locations":
                        c.execute("INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
                                  (src_table, row.get("id"), "locations", dst_id, "located_at", 1.0))
                        link_count += 1
    c.execute("CREATE VIRTUAL TABLE entities_fts USING fts5(table_name, id, name, blob, extra, tokenize='unicode61 remove_diacritics 2')")
    c.execute("INSERT INTO entities_fts(table_name, id, name, blob, extra) SELECT table_name, id, name, blob, extra FROM entities")
    c.execute("INSERT INTO data_versions VALUES ('schema', '5.5-fts-links-issues', ?)", (now,))
    conn.commit()
    conn.close()
    return {"records": total, "links": link_count, "version": ver, "db": str(path), "issues_logged": True}

if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))

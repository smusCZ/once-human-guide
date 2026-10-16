#!/usr/bin/env python3
"""Build once_human.db from module JSON or database_full.json.

Adds indexes, unified entity catalog, FTS5 (unicode61 remove_diacritics),
richer name/id links (ingredients, drops, locations, sources), data_issues audit.
User-layer data is never written here (separate once_human_user.db).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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

SCHEMAS = {
    "deviations": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, rarity TEXT, utility TEXT, desc TEXT, mood TEXT, source TEXT, tags TEXT",
                   ["id", "name", "type", "rarity", "utility", "desc", "mood", "source", "tags"]),
    "weapons": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, rarity TEXT, style TEXT, desc TEXT, tags TEXT",
                ["id", "name", "type", "rarity", "style", "desc", "tags"]),
    "armor": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, rarity TEXT, style TEXT, pieces TEXT, desc TEXT, tags TEXT",
              ["id", "name", "type", "rarity", "style", "pieces", "desc", "tags"]),
    "mods": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, rarity TEXT, slot TEXT, desc TEXT, source TEXT, tags TEXT",
             ["id", "name", "type", "rarity", "slot", "desc", "source", "tags"]),
    "bosses": ("id TEXT PRIMARY KEY, name TEXT, region TEXT, location TEXT, desc TEXT, drops TEXT",
               ["id", "name", "region", "location", "desc", "drops"]),
    "locations": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, region TEXT, x REAL, y REAL, desc TEXT",
                  ["id", "name", "type", "region", "x", "y", "desc"]),
    "recipes": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, station TEXT, ingredients TEXT, effect TEXT, desc TEXT",
                ["id", "name", "type", "station", "ingredients", "effect", "desc"]),
    "materials": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, desc TEXT",
                  ["id", "name", "type", "desc"]),
    "scenarios": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, phase TEXT, desc TEXT, rewards TEXT, locations TEXT, tags TEXT",
                  ["id", "name", "type", "phase", "desc", "rewards", "locations", "tags"]),
    "quests": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, region TEXT, desc TEXT, rewards TEXT, tags TEXT",
               ["id", "name", "type", "region", "desc", "rewards", "tags"]),
    "events": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, status TEXT, desc TEXT, rewards TEXT, location TEXT, timer TEXT, tags TEXT",
               ["id", "name", "type", "status", "desc", "rewards", "location", "timer", "tags"]),
    "creatures": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, threat TEXT, desc TEXT, location TEXT, tags TEXT",
                  ["id", "name", "type", "threat", "desc", "location", "tags"]),
    "npcs": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, location TEXT, desc TEXT, tags TEXT",
             ["id", "name", "type", "location", "desc", "tags"]),
    "plants": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, desc TEXT, uses TEXT, tags TEXT",
               ["id", "name", "type", "desc", "uses", "tags"]),
    "fish": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, desc TEXT, location TEXT, tags TEXT",
             ["id", "name", "type", "desc", "location", "tags"]),
    "animals": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, desc TEXT, drops TEXT, location TEXT, taming TEXT, tags TEXT",
                ["id", "name", "type", "desc", "drops", "location", "taming", "tags"]),
    "flowers": ("id TEXT PRIMARY KEY, name TEXT, type TEXT, desc TEXT, tags TEXT",
                ["id", "name", "type", "desc", "tags"]),
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
    s = (name or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


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
        table_name TEXT NOT NULL,
        id TEXT NOT NULL,
        name TEXT,
        kind TEXT,
        rarity TEXT,
        region TEXT,
        blob TEXT,
        PRIMARY KEY (table_name, id)
    )""")
    c.execute("""CREATE TABLE links (
        src_table TEXT, src_id TEXT, dst_table TEXT, dst_id TEXT,
        relation TEXT, score REAL,
        PRIMARY KEY (src_table, src_id, dst_table, dst_id, relation)
    )""")
    c.execute("""CREATE TABLE data_issues (
        table_name TEXT, id TEXT, issue TEXT, detail TEXT,
        PRIMARY KEY (table_name, id, issue)
    )""")

    total = 0
    catalog = []
    issues = 0
    by_name: dict[str, list[tuple[str, str]]] = {}
    by_id: dict[str, list[tuple[str, str]]] = {}

    for table, (schema, cols) in SCHEMAS.items():
        c.execute(f"CREATE TABLE {table} ({schema})")
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_name ON {table}(name)")
        if "type" in cols:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_type ON {table}(type)")
        if "rarity" in cols:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_rarity ON {table}(rarity)")
        if "region" in cols:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_region ON {table}(region)")
        if "slot" in cols:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_slot ON {table}(slot)")

        seen_ids = set()
        for row in data.get(table, []):
            rid = row.get("id")
            name = row.get("name") or ""
            if not rid:
                c.execute("INSERT OR IGNORE INTO data_issues VALUES (?,?,?,?)",
                          (table, "", "missing_id", ""))
                issues += 1
                continue
            if rid in seen_ids:
                c.execute("INSERT OR IGNORE INTO data_issues VALUES (?,?,?,?)",
                          (table, rid, "duplicate_id", ""))
                issues += 1
            seen_ids.add(rid)
            if not name.strip():
                c.execute("INSERT OR IGNORE INTO data_issues VALUES (?,?,?,?)",
                          (table, rid, "empty_name", ""))
                issues += 1

            vals = []
            for col in cols:
                value = row.get(col)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                vals.append(value)
            c.execute(
                f"INSERT OR REPLACE INTO {table} VALUES ({','.join('?' * len(cols))})",
                vals,
            )
            catalog.append((table, row))
            total += 1
            key = _norm(name)
            if key:
                by_name.setdefault(key, []).append((table, rid))
            by_id.setdefault(rid, []).append((table, rid))

            c.execute(
                "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?)",
                (
                    table,
                    rid,
                    name,
                    row.get("type") or row.get("utility") or "",
                    row.get("rarity") or "",
                    row.get("region") or row.get("location") or "",
                    _blob(row),
                ),
            )

    # Links: ingredients, drops, locations, sources, rewards
    link_count = 0

    def add_link(src_table, src_id, dst_table, dst_id, relation, score=1.0):
        nonlocal link_count
        if not src_id or not dst_id or (src_table, src_id) == (dst_table, dst_id):
            return
        c.execute(
            "INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
            (src_table, src_id, dst_table, dst_id, relation, score),
        )
        link_count += 1

    def resolve_name(label: str):
        return by_name.get(_norm(label), [])

    # Recipes -> ingredients
    for row in data.get("recipes", []):
        ingredients = row.get("ingredients") or []
        if isinstance(ingredients, str):
            try:
                ingredients = json.loads(ingredients)
            except json.JSONDecodeError:
                ingredients = []
        for ing in ingredients:
            label = ing.get("name") if isinstance(ing, dict) else str(ing)
            for dst_table, dst_id in resolve_name(label):
                if dst_table != "recipes":
                    add_link("recipes", row.get("id"), dst_table, dst_id, "ingredient")

    # Bosses drops, animals drops, scenarios rewards, quests rewards, events rewards
    for table, field, relation in [
        ("bosses", "drops", "drops"),
        ("animals", "drops", "drops"),
        ("scenarios", "rewards", "reward"),
        ("quests", "rewards", "reward"),
        ("events", "rewards", "reward"),
    ]:
        for row in data.get(table, []):
            items = row.get(field) or []
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except json.JSONDecodeError:
                    items = []
            for item in items:
                label = item.get("name") if isinstance(item, dict) else str(item)
                for dst_table, dst_id in resolve_name(label):
                    add_link(table, row.get("id"), dst_table, dst_id, relation)

    # Location / source / region references
    for table in SCHEMAS:
        for row in data.get(table, []):
            for field, relation in [("location", "located_at"), ("source", "source"), ("region", "in_region")]:
                val = row.get(field)
                if not val or not isinstance(val, str):
                    continue
                for dst_table, dst_id in resolve_name(val):
                    if dst_table in ("locations", "npcs", "bosses"):
                        add_link(table, row.get("id"), dst_table, dst_id, relation)

    # FTS with diacritic removal for Czech-friendly search
    c.execute("""CREATE VIRTUAL TABLE entities_fts USING fts5(
        table_name, id, name, blob,
        tokenize='unicode61 remove_diacritics 2'
    )""")
    c.execute("INSERT INTO entities_fts(table_name, id, name, blob) SELECT table_name, id, name, blob FROM entities")

    c.execute("INSERT INTO data_versions VALUES ('schema', '5.5-fts-links-audit', ?)", (now,))
    conn.commit()
    conn.close()
    return {
        "records": total,
        "links": link_count,
        "issues": issues,
        "version": ver,
        "db": str(path),
        "schema": "5.5-fts-links-audit",
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))

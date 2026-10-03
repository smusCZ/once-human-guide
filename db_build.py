#!/usr/bin/env python3
"""Build once_human.db from module JSON or database_full.json.

Adds indexes, a unified entity catalog, FTS5 search, name-based links,
and a user layer (favorites / inventory / builds / queue) that survives rebuilds.
User-layer data is never written into the pack.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
SCHEMA = "5.5-user-layer"

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

USER_DDL = [
    """CREATE TABLE IF NOT EXISTS favorites (
        table_name TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (table_name, entity_id)
    )""",
    """CREATE TABLE IF NOT EXISTS inventory (
        table_name TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        qty REAL NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (table_name, entity_id)
    )""",
    """CREATE TABLE IF NOT EXISTS builds (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS review_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )""",
]


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
    return " ".join((name or "").lower().replace("-", " ").replace("_", " ").split())


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
    if isinstance(value, list):
        return value
    return [value]


def _snapshot_user(path: Path) -> dict:
    empty = {"favorites": [], "inventory": [], "builds": [], "review_queue": []}
    if not path.exists():
        return empty
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for key in empty:
            try:
                empty[key] = [dict(r) for r in conn.execute(f"SELECT * FROM {key}")]
            except sqlite3.Error:
                empty[key] = []
    finally:
        conn.close()
    return empty


def _restore_user(conn: sqlite3.Connection, snap: dict, now: str) -> None:
    for ddl in USER_DDL:
        conn.execute(ddl)
    for row in snap.get("favorites") or []:
        conn.execute(
            "INSERT OR REPLACE INTO favorites VALUES (?,?,?,?)",
            (row.get("table_name"), row.get("entity_id"), row.get("note"), row.get("created_at") or now),
        )
    for row in snap.get("inventory") or []:
        conn.execute(
            "INSERT OR REPLACE INTO inventory VALUES (?,?,?,?)",
            (row.get("table_name"), row.get("entity_id"), row.get("qty") or 1, row.get("updated_at") or now),
        )
    for row in snap.get("builds") or []:
        conn.execute(
            "INSERT OR REPLACE INTO builds VALUES (?,?,?,?)",
            (row.get("id"), row.get("name"), row.get("payload") or "{}", row.get("updated_at") or now),
        )
    for row in snap.get("review_queue") or []:
        conn.execute(
            "INSERT INTO review_queue (kind, payload, status, created_at) VALUES (?,?,?,?)",
            (row.get("kind") or "note", row.get("payload") or "{}", row.get("status") or "pending", row.get("created_at") or now),
        )


def _add_link(conn, src_table, src_id, dst_table, dst_id, relation) -> int:
    if not src_id or not dst_id or (src_table == dst_table and src_id == dst_id):
        return 0
    cur = conn.execute(
        "INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
        (src_table, src_id, dst_table, dst_id, relation, 1.0),
    )
    return cur.rowcount or 0


def build(db_path: Path | None = None) -> dict:
    data = load_pack()
    path = db_path or DB_PATH
    snap = _snapshot_user(path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    ver = data.get("version", "unknown")
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "CREATE TABLE data_versions (table_name TEXT PRIMARY KEY, version TEXT, updated_at TEXT)"
    )
    c.execute("INSERT INTO data_versions VALUES ('all', ?, ?)", (ver, now))
    c.execute(
        """CREATE TABLE entities (
            table_name TEXT NOT NULL,
            id TEXT NOT NULL,
            name TEXT,
            kind TEXT,
            rarity TEXT,
            region TEXT,
            blob TEXT,
            PRIMARY KEY (table_name, id)
        )"""
    )
    c.execute("CREATE INDEX idx_entities_name ON entities(name)")
    c.execute("CREATE INDEX idx_entities_kind ON entities(kind)")
    c.execute(
        """CREATE TABLE links (
            src_table TEXT, src_id TEXT, dst_table TEXT, dst_id TEXT,
            relation TEXT, score REAL,
            PRIMARY KEY (src_table, src_id, dst_table, dst_id, relation)
        )"""
    )
    c.execute("CREATE INDEX idx_links_dst ON links(dst_table, dst_id)")
    total = 0
    dupes = []
    catalog = []
    for table, (schema, cols) in SCHEMAS.items():
        c.execute(f"CREATE TABLE {table} ({schema})")
        c.execute(f"CREATE INDEX idx_{table}_name ON {table}(name)")
        if "type" in cols:
            c.execute(f"CREATE INDEX idx_{table}_type ON {table}(type)")
        if "rarity" in cols:
            c.execute(f"CREATE INDEX idx_{table}_rarity ON {table}(rarity)")
        seen = set()
        for row in data.get(table, []):
            rid = row.get("id")
            if rid in seen:
                dupes.append({"table": table, "id": rid})
            seen.add(rid)
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
    by_name: dict[str, list[tuple[str, str]]] = {}
    for table, row in catalog:
        name = row.get("name") or ""
        c.execute(
            "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?)",
            (
                table,
                row.get("id"),
                name,
                row.get("type") or row.get("utility") or "",
                row.get("rarity") or "",
                row.get("region") or row.get("location") or "",
                _blob(row),
            ),
        )
        key = _norm(name)
        if key:
            by_name.setdefault(key, []).append((table, row.get("id")))
    link_count = 0

    def resolve(label: str):
        return by_name.get(_norm(label)) or []

    for row in data.get("recipes", []):
        for ing in _as_list(row.get("ingredients")):
            label = ing.get("name") if isinstance(ing, dict) else str(ing)
            for dst_table, dst_id in resolve(label):
                if dst_table == "recipes":
                    continue
                link_count += _add_link(c, "recipes", row.get("id"), dst_table, dst_id, "ingredient")
    for table, field, relation in (
        ("bosses", "drops", "drops"),
        ("animals", "drops", "drops"),
        ("quests", "rewards", "rewards"),
        ("events", "rewards", "rewards"),
        ("scenarios", "rewards", "rewards"),
    ):
        for row in data.get(table, []):
            for item in _as_list(row.get(field)):
                label = item.get("name") if isinstance(item, dict) else str(item)
                for dst_table, dst_id in resolve(label):
                    link_count += _add_link(c, table, row.get("id"), dst_table, dst_id, relation)
    for table in ("bosses", "quests", "events", "creatures", "npcs", "fish", "animals"):
        for row in data.get(table, []):
            for item in _as_list(row.get("location") or row.get("locations")):
                label = item.get("name") if isinstance(item, dict) else str(item)
                for dst_table, dst_id in resolve(label):
                    if dst_table != "locations":
                        continue
                    link_count += _add_link(c, table, row.get("id"), dst_table, dst_id, "located_at")
    c.execute(
        "CREATE VIRTUAL TABLE entities_fts USING fts5(table_name, id, name, blob, tokenize='unicode61')"
    )
    c.execute(
        "INSERT INTO entities_fts(table_name, id, name, blob) SELECT table_name, id, name, blob FROM entities"
    )
    _restore_user(conn, snap, now)
    c.execute("INSERT INTO data_versions VALUES ('schema', ?, ?)", (SCHEMA, now))
    c.execute(
        "INSERT INTO data_versions VALUES ('dupes', ?, ?)",
        (json.dumps(dupes, ensure_ascii=False), now),
    )
    conn.commit()
    conn.close()
    return {
        "records": total,
        "links": link_count,
        "version": ver,
        "schema": SCHEMA,
        "dupes": len(dupes),
        "user_favorites": len(snap.get("favorites") or []),
        "db": str(path),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))

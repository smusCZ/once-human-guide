#!/usr/bin/env python3
"""Build once_human.db from module JSON or database_full.json.

Pack is read-only. User favorites/builds live in once_human_user.db.
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
USER_DB_PATH = BASE / "once_human_user.db"

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

LINK_FIELDS = {
    "recipes": ("ingredients", "ingredient"),
    "bosses": ("drops", "drop"),
    "animals": ("drops", "drop"),
    "quests": ("rewards", "reward"),
    "events": ("rewards", "reward"),
    "scenarios": ("rewards", "reward"),
    "scenarios_locations": ("locations", "located_in"),
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


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


def load_meta() -> dict:
    path = BASE / "version.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_pack() -> dict:
    full = BASE / "database_full.json"
    if full.exists():
        data = json.loads(full.read_text(encoding="utf-8"))
        if isinstance(data, dict) and any(k in data for k in MODULES):
            data["version"] = load_meta().get("data_version", data.get("version", "local"))
            return data
    data = _load_modules()
    data["version"] = load_meta().get("data_version", "local")
    return data


def _blob(row: dict) -> str:
    parts = []
    for value in row.values():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts)


def _as_labels(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
    if isinstance(value, dict):
        value = [value]
    labels = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                labels.append(str(item.get("name") or item.get("id") or ""))
            else:
                labels.append(str(item))
    return [label for label in labels if label.strip()]


def ensure_user_db(path: Path | None = None) -> Path:
    path = path or USER_DB_PATH
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_items (
            kind TEXT NOT NULL,
            table_name TEXT NOT NULL,
            item_id TEXT NOT NULL,
            payload TEXT,
            updated_at TEXT,
            PRIMARY KEY (kind, table_name, item_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_notes (
            table_name TEXT NOT NULL,
            item_id TEXT NOT NULL,
            note TEXT,
            updated_at TEXT,
            PRIMARY KEY (table_name, item_id)
        )"""
    )
    conn.commit()
    conn.close()
    return path


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
    c.execute(
        """CREATE TABLE entities (
            table_name TEXT NOT NULL,
            id TEXT NOT NULL,
            name TEXT,
            name_fold TEXT,
            kind TEXT,
            rarity TEXT,
            region TEXT,
            blob TEXT,
            PRIMARY KEY (table_name, id)
        )"""
    )
    c.execute(
        """CREATE TABLE links (
            src_table TEXT, src_id TEXT, dst_table TEXT, dst_id TEXT,
            relation TEXT, score REAL,
            PRIMARY KEY (src_table, src_id, dst_table, dst_id, relation)
        )"""
    )
    c.execute(
        """CREATE TABLE data_issues (
            table_name TEXT, item_id TEXT, issue TEXT, detail TEXT
        )"""
    )
    total = 0
    catalog = []
    seen = set()
    for table, (schema, cols) in SCHEMAS.items():
        c.execute(f"CREATE TABLE {table} ({schema})")
        c.execute(f"CREATE INDEX idx_{table}_name ON {table}(name)")
        for row in data.get(table, []):
            item_id = row.get("id")
            key = (table, item_id)
            if not item_id or key in seen:
                c.execute(
                    "INSERT INTO data_issues VALUES (?,?,?,?)",
                    (table, item_id or "", "duplicate_or_missing_id", item_id or ""),
                )
            seen.add(key)
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
            "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?)",
            (
                table,
                row.get("id"),
                name,
                fold(name),
                row.get("type") or row.get("utility") or "",
                row.get("rarity") or "",
                row.get("region") or row.get("location") or "",
                _blob(row),
            ),
        )
        key = fold(name)
        if key:
            by_name.setdefault(key, []).append((table, row.get("id")))
        if row.get("id"):
            by_name.setdefault(fold(str(row.get("id"))), []).append((table, row.get("id")))
    link_count = 0
    unresolved = 0
    for table, row in catalog:
        fields = []
        if table in LINK_FIELDS:
            fields.append(LINK_FIELDS[table])
        if table == "scenarios":
            fields.append(("locations", "located_in"))
        if table in ("creatures", "npcs", "fish", "animals", "bosses", "events"):
            fields.append(("location", "located_in"))
        for field, relation in fields:
            for label in _as_labels(row.get(field)):
                hit = by_name.get(fold(label))
                if not hit:
                    unresolved += 1
                    c.execute(
                        "INSERT INTO data_issues VALUES (?,?,?,?)",
                        (table, row.get("id"), "unresolved_" + relation, label),
                    )
                    continue
                for dst_table, dst_id in hit:
                    if dst_table == table and dst_id == row.get("id"):
                        continue
                    c.execute(
                        "INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
                        (table, row.get("id"), dst_table, dst_id, relation, 1.0),
                    )
                    link_count += 1
    c.execute("CREATE INDEX idx_links_src ON links(src_table, src_id)")
    c.execute("CREATE INDEX idx_links_dst ON links(dst_table, dst_id)")
    c.execute("CREATE INDEX idx_entities_fold ON entities(name_fold)")
    c.execute(
        "CREATE VIRTUAL TABLE entities_fts USING fts5(table_name, id, name, blob, tokenize='unicode61 remove_diacritics 2')"
    )
    c.execute(
        "INSERT INTO entities_fts(table_name, id, name, blob) SELECT table_name, id, name, blob FROM entities"
    )
    c.execute("INSERT INTO data_versions VALUES ('schema', '5.7-fold-links-user', ?)", (now,))
    conn.commit()
    conn.close()
    ensure_user_db()
    expected = load_meta().get("records")
    return {
        "records": total,
        "links": link_count,
        "unresolved": unresolved,
        "version": ver,
        "expected": expected,
        "ok": expected is None or total == expected,
        "db": str(path),
        "user_db": str(USER_DB_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))

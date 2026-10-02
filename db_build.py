#!/usr/bin/env python3
"""Build once_human.db from module JSON or database_full.json.

Adds indexes, a unified entity catalog, FTS5 search, name-based links,
and an integrity report. User-layer data is never written here.
Pack JSON is read-only.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
SCHEMA_VERSION = "5.5-graph-integrity"

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
    "deviations": ("source", "source"),
    "mods": ("source", "source"),
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
    return " ".join((name or "").lower().replace("-", " ").replace("_", " ").split())


def _labels(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text[:1] in "[{":
            try:
                return _labels(json.loads(text))
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, dict):
        label = value.get("name") or value.get("id") or ""
        return [str(label)] if label else []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_labels(item))
        return out
    return [str(value)]


def _add_link(c, seen, src_table, src_id, dst_table, dst_id, relation, score=1.0) -> bool:
    if not src_id or not dst_id:
        return False
    if src_table == dst_table and src_id == dst_id:
        return False
    key = (src_table, src_id, dst_table, dst_id, relation)
    if key in seen:
        return False
    seen.add(key)
    c.execute(
        "INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
        (src_table, src_id, dst_table, dst_id, relation, score),
    )
    return True


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
    c.execute(
        "CREATE TABLE data_versions (table_name TEXT PRIMARY KEY, version TEXT, updated_at TEXT)"
    )
    c.execute("INSERT INTO data_versions VALUES ('all', ?, ?)", (ver, now))
    c.execute(
        """CREATE TABLE entities (\n            table_name TEXT NOT NULL,\n            id TEXT NOT NULL,\n            name TEXT,\n            kind TEXT,\n            rarity TEXT,\n            region TEXT,\n            blob TEXT,\n            PRIMARY KEY (table_name, id)\n        )"""
    )
    c.execute(
        """CREATE TABLE links (\n            src_table TEXT, src_id TEXT, dst_table TEXT, dst_id TEXT,\n            relation TEXT, score REAL,\n            PRIMARY KEY (src_table, src_id, dst_table, dst_id, relation)\n        )"""
    )
    c.execute(
        """CREATE TABLE integrity_findings (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            severity TEXT,\n            table_name TEXT,\n            item_id TEXT,\n            code TEXT,\n            detail TEXT\n        )"""
    )
    total = 0
    catalog = []
    seen_ids: dict[str, set[str]] = {}
    for table, (schema, cols) in SCHEMAS.items():
        c.execute(f"CREATE TABLE {table} ({schema})")
        c.execute(f"CREATE INDEX idx_{table}_name ON {table}(name)")
        seen_ids[table] = set()
        for row in data.get(table, []):
            item_id = row.get("id")
            if not item_id:
                c.execute(
                    "INSERT INTO integrity_findings (severity, table_name, item_id, code, detail) VALUES (?,?,?,?,?)",
                    ("error", table, "", "missing_id", "row without id skipped from catalog key"),
                )
            elif item_id in seen_ids[table]:
                c.execute(
                    "INSERT INTO integrity_findings (severity, table_name, item_id, code, detail) VALUES (?,?,?,?,?)",
                    ("error", table, item_id, "duplicate_id", "duplicate id in pack; last row wins"),
                )
            else:
                seen_ids[table].add(item_id)
            if not (row.get("name") or "").strip():
                c.execute(
                    "INSERT INTO integrity_findings (severity, table_name, item_id, code, detail) VALUES (?,?,?,?,?)",
                    ("warn", table, item_id or "", "empty_name", "name is empty"),
                )
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
    seen_links: set[tuple] = set()
    link_count = 0
    unresolved = 0
    for table, (field, relation) in LINK_FIELDS.items():
        for row in data.get(table, []):
            for label in _labels(row.get(field)):
                hit = by_name.get(_norm(label))
                if not hit:
                    unresolved += 1
                    continue
                for dst_table, dst_id in hit:
                    if _add_link(c, seen_links, table, row.get("id"), dst_table, dst_id, relation):
                        link_count += 1
    for table in ("bosses", "creatures", "npcs", "quests", "events", "fish", "animals"):
        for row in data.get(table, []):
            for label in _labels(row.get("location") or row.get("region")):
                hit = [item for item in by_name.get(_norm(label), []) if item[0] == "locations"]
                if not hit:
                    continue
                for dst_table, dst_id in hit:
                    if _add_link(c, seen_links, table, row.get("id"), dst_table, dst_id, "located_at", 0.8):
                        link_count += 1
    if unresolved:
        c.execute(
            "INSERT INTO integrity_findings (severity, table_name, item_id, code, detail) VALUES (?,?,?,?,?)",
            ("info", "links", "", "unresolved_labels", f"{unresolved} ingredient/drop/source labels had no name match"),
        )
    c.execute(
        "CREATE VIRTUAL TABLE entities_fts USING fts5(table_name, id, name, blob, tokenize='unicode61')"
    )
    c.execute(
        "INSERT INTO entities_fts(table_name, id, name, blob) SELECT table_name, id, name, blob FROM entities"
    )
    c.execute(
        "INSERT INTO data_versions VALUES ('schema', ?, ?)",
        (SCHEMA_VERSION, now),
    )
    findings = c.execute("SELECT COUNT(*) FROM integrity_findings").fetchone()[0]
    conn.commit()
    conn.close()
    return {
        "records": total,
        "links": link_count,
        "findings": findings,
        "version": ver,
        "schema": SCHEMA_VERSION,
        "db": str(path),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))

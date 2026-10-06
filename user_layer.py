#!/usr/bin/env python3
"""User layer store. Never written by db_build — pack rebuild cannot wipe it."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
USER_DB = BASE / "user_layer.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS favorites (
          table_name TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          note TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY (table_name, entity_id)
        );
        CREATE TABLE IF NOT EXISTS inventory (
          table_name TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          qty INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (table_name, entity_id)
        );
        CREATE TABLE IF NOT EXISTS progress (
          key TEXT PRIMARY KEY,
          done INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS builds (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          payload TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def summary() -> dict:
    conn = connect()
    try:
        return {
            "favorites": conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0],
            "inventory": conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
            "progress_done": conn.execute("SELECT COUNT(*) FROM progress WHERE done=1").fetchone()[0],
            "builds": conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0],
            "db": str(USER_DB),
        }
    finally:
        conn.close()


def list_table(name: str) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(f"SELECT * FROM {name}").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_favorite(table: str, entity_id: str, note: str | None = None) -> dict:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO favorites VALUES (?,?,?,?) ON CONFLICT(table_name, entity_id) DO UPDATE SET note=excluded.note",
            (table, entity_id, note or "", _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def delete_favorite(table: str, entity_id: str) -> dict:
    conn = connect()
    try:
        conn.execute("DELETE FROM favorites WHERE table_name=? AND entity_id=?", (table, entity_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def upsert_inventory(table: str, entity_id: str, qty: int) -> dict:
    conn = connect()
    try:
        if qty <= 0:
            conn.execute("DELETE FROM inventory WHERE table_name=? AND entity_id=?", (table, entity_id))
        else:
            conn.execute(
                """INSERT INTO inventory VALUES (?,?,?,?)
                   ON CONFLICT(table_name, entity_id) DO UPDATE SET qty=excluded.qty, updated_at=excluded.updated_at""",
                (table, entity_id, qty, _now()),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def save_build(build_id: str, name: str, payload: dict) -> dict:
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO builds VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, payload=excluded.payload, updated_at=excluded.updated_at""",
            (build_id, name, json.dumps(payload, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}

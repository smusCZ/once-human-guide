"""Pack count and user-layer survival. Does not touch ohg_data.js."""
import json
from pathlib import Path

import db_build

ROOT = Path(__file__).resolve().parent


def test_pack_modules_present():
    missing = [name for name in db_build.MODULES.values() if not (ROOT / name).exists()]
    assert not missing, missing


def test_build_keeps_expected_records(tmp_path):
    out = db_build.build(tmp_path / "once_human.db")
    assert out["records"] == 372
    assert out["dupes"] == 0
    assert out["links"] >= 1
    assert out["schema"] == "5.5-user-layer"


def test_user_layer_survives_rebuild(tmp_path):
    path = tmp_path / "once_human.db"
    db_build.build(path)
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO favorites VALUES (?,?,?,?)",
        ("weapons", "demo", "keep me", "2026-10-03T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    again = db_build.build(path)
    assert again["records"] == 372
    assert again["user_favorites"] == 1
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT note FROM favorites WHERE entity_id='demo'").fetchone()
    conn.close()
    assert row[0] == "keep me"


def test_version_json_records():
    meta = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    assert meta["records"] == 372
    assert meta["app_version"] == "5.5.0"

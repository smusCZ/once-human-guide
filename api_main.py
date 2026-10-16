"""Once Human Guide API — FastAPI + SQLite + FTS (diacritics) + static shell + user layer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
if not DB_PATH.exists():
    DB_PATH = BASE.parent / "once_human.db"
USER_DB_PATH = BASE / "once_human_user.db"

def load_version():
    path = BASE / "version.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"app_version": "5.5.0", "data_version": "local", "shell_version": "19.4"}

VERSION = load_version()
API_VERSION = VERSION.get("app_version", "5.5.0")
DATA_VERSION = VERSION.get("data_version", "local")
MAP_EMBEDS = {
    "thgl": "https://oncehuman.th.gl",
    "mapgenie": "https://mapgenie.io/once-human/maps/nalcott",
}

TABLES = [
    "deviations", "weapons", "armor", "mods", "bosses", "locations",
    "recipes", "materials", "scenarios", "quests", "events", "creatures",
    "npcs", "plants", "fish", "animals", "flowers",
]

app = FastAPI(
    title="Once Human Guide API",
    version=API_VERSION,
    description="Game companion data API for Once Human Guide",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if (BASE / "modules").is_dir():
    app.mount("/modules", StaticFiles(directory=BASE / "modules"), name="modules")


def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, f"Database not found at {DB_PATH}. Run python db_build.py")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_user_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(USER_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
        table_name TEXT, item_id TEXT, note TEXT, created_at TEXT,
        PRIMARY KEY (table_name, item_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notes (
        table_name TEXT, item_id TEXT, note TEXT, updated_at TEXT,
        PRIMARY KEY (table_name, item_id)
    )""")
    conn.commit()
    return conn


def rows_to_list(rows) -> list[dict]:
    items = [dict(r) for r in rows]
    for item in items:
        for key in ("tags", "ingredients", "drops", "locations", "pieces", "rewards"):
            if key in item and isinstance(item[key], str):
                try:
                    item[key] = json.loads(item[key] or "[]")
                except Exception:
                    pass
    return items


def fetch_all(table: str, q: str | None = None, limit: int = 500, offset: int = 0,
              rarity: str | None = None, typ: str | None = None, region: str | None = None, slot: str | None = None) -> list[dict]:
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    try:
        where = []
        params = []
        if q:
            where.append("(lower(name) LIKE ? OR lower(coalesce(desc,'')) LIKE ?)")
            params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
        if rarity:
            where.append("lower(coalesce(rarity,'')) = ?")
            params.append(rarity.lower())
        if typ:
            where.append("lower(coalesce(type,'')) = ?")
            params.append(typ.lower())
        if region:
            where.append("lower(coalesce(region,location,'')) LIKE ?")
            params.append(f"%{region.lower()}%")
        if slot:
            where.append("lower(coalesce(slot,'')) = ?")
            params.append(slot.lower())
        sql = f"SELECT * FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        raise HTTPException(500, str(exc)) from exc
    conn.close()
    return rows_to_list(rows)


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "Once Human Guide API",
        "api_version": API_VERSION,
        "data_version": DATA_VERSION,
        "shell_version": VERSION.get("shell_version"),
        "tables": TABLES,
        "endpoints": {
            "ui": "/ui",
            "health": "/health",
            "version": "/version",
            "stats": "/stats",
            "search": "/search?q=",
            "integrity": "/integrity",
            "audit": "/audit",
            "links": "/links/{table}/{id}",
            "export": "/export",
            "maps": "/maps",
            "user": "/user/favorites",
        },
    }


@app.get("/health")
def health():
    ok = DB_PATH.exists()
    return {"ok": ok, "db": str(DB_PATH), "api_version": API_VERSION, "data_version": DATA_VERSION}


@app.get("/ui")
def serve_ui():
    for name in (
        "once_human_guide_v19.html",
        "once_human_guide_v18.html",
        "once_human_guide_ui_v4.html",
        "once_human_guide_app.html",
    ):
        html = BASE / name
        if html.exists():
            return HTMLResponse(html.read_text(encoding="utf-8"))
    raise HTTPException(404, "UI HTML not found")


@app.get("/ohg_data.js")
def pack_js():
    path = BASE / "ohg_data.js"
    if not path.exists():
        raise HTTPException(404, "ohg_data.js missing")
    return FileResponse(path, media_type="application/javascript")


@app.get("/ohg_sw.js")
def sw_js():
    path = BASE / "ohg_sw.js"
    if not path.exists():
        raise HTTPException(404, "ohg_sw.js missing")
    return FileResponse(path, media_type="application/javascript")


@app.get("/version")
def version():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT version, updated_at FROM data_versions WHERE table_name='all'"
        ).fetchone()
        ver = row["version"] if row else DATA_VERSION
        updated = row["updated_at"] if row else None
    except Exception:
        ver, updated = DATA_VERSION, None
    finally:
        conn.close()
    return {
        "data_version": ver,
        "api_version": API_VERSION,
        "shell_version": VERSION.get("shell_version"),
        "updated_at": updated,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "maps": MAP_EMBEDS,
        "notes": VERSION.get("notes"),
    }


@app.get("/maps")
def maps():
    return {"embeds": MAP_EMBEDS, "local_markers": True}


@app.get("/stats")
def stats():
    conn = get_db()
    out = {}
    total = 0
    for table in TABLES:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            n = 0
        out[table] = n
        total += n
    try:
        out["links"] = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        out["fts"] = conn.execute("SELECT COUNT(*) FROM entities_fts").fetchone()[0]
        out["issues"] = conn.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0]
    except Exception:
        out["links"] = out["fts"] = out["issues"] = 0
    conn.close()
    out["total"] = total
    out["data_version"] = DATA_VERSION
    out["api_version"] = API_VERSION
    return out


@app.get("/integrity")
def integrity():
    conn = get_db()
    issues = []
    counts = {}
    for table in TABLES:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            empty = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE name IS NULL OR trim(name)=''"
            ).fetchone()[0]
        except sqlite3.Error as exc:
            issues.append({"table": table, "error": str(exc)})
            continue
        counts[table] = n
        if empty:
            issues.append({"table": table, "empty_names": empty})
    quick = conn.execute("PRAGMA quick_check").fetchone()[0]
    try:
        stored = conn.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0]
    except Exception:
        stored = 0
    conn.close()
    return {
        "ok": quick == "ok" and not issues and stored == 0,
        "quick_check": quick,
        "counts": counts,
        "issues": issues,
        "stored_issues": stored,
        "expected_records": 372,
    }


@app.get("/audit")
def audit():
    conn = get_db()
    try:
        rows = conn.execute("SELECT table_name, id, issue, detail FROM data_issues ORDER BY table_name, id").fetchall()
        issues = [dict(r) for r in rows]
    except Exception:
        issues = []
    conn.close()
    return {"count": len(issues), "issues": issues}


@app.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=200), table: str | None = None):
    conn = get_db()
    # Safe token for FTS
    tokens = re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE).split()
    fts_q = " OR ".join(f'"{t}"*' for t in tokens if t) or q
    try:
        sql = """SELECT table_name, id, name, blob FROM entities_fts WHERE entities_fts MATCH ?"""
        params = [fts_q]
        if table and table in TABLES:
            sql += " AND table_name = ?"
            params.append(table)
        sql += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        mode = "fts"
    except sqlite3.Error:
        like = f"%{q.lower()}%"
        sql = "SELECT table_name, id, name, blob FROM entities WHERE lower(name) LIKE ? OR lower(blob) LIKE ?"
        params = [like, like]
        if table and table in TABLES:
            sql += " AND table_name = ?"
            params.append(table)
        sql += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        mode = "like"
    conn.close()
    results = [
        {"table": r["table_name"], "id": r["id"], "name": r["name"], "snippet": (r["blob"] or "")[:180]}
        for r in rows
    ]
    return {"q": q, "mode": mode, "count": len(results), "results": results, "table": table}


@app.get("/links/{table}/{item_id}")
def links(table: str, item_id: str):
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT dst_table AS other_table, dst_id AS other_id, relation, score, 'out' AS direction FROM links
               WHERE src_table=? AND src_id=?
               UNION
               SELECT src_table, src_id, relation, score, 'in' FROM links
               WHERE dst_table=? AND dst_id=?""",
            (table, item_id, table, item_id),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # Resolve name
            name_row = conn.execute(
                "SELECT name FROM entities WHERE table_name=? AND id=?",
                (d["other_table"], d["other_id"]),
            ).fetchone()
            d["other_name"] = name_row["name"] if name_row else d["other_id"]
            out.append(d)
    except sqlite3.Error:
        out = []
    conn.close()
    return {"table": table, "id": item_id, "links": out}


@app.get("/export")
def export_all():
    data = {"version": DATA_VERSION, "exported_at": datetime.now(timezone.utc).isoformat()}
    for table in TABLES:
        data[table] = fetch_all(table, limit=2000)
    return data


@app.get("/db-file")
def db_file():
    if not DB_PATH.exists():
        raise HTTPException(404, "SQLite file missing")
    return FileResponse(str(DB_PATH), filename="once_human.db")


def _list(table: str, q: str | None = None, limit: int = 500, offset: int = 0, **filters):
    return fetch_all(table, q, limit, offset, **filters)


@app.get("/deviations")
def list_deviations(type: str | None = None, rarity: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("deviations", q, limit, offset, typ=type, rarity=rarity)


@app.get("/weapons")
def list_weapons(rarity: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("weapons", q, limit, offset, rarity=rarity)


@app.get("/armor")
def list_armor(rarity: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("armor", q, limit, offset, rarity=rarity)


@app.get("/mods")
def list_mods(slot: str | None = None, rarity: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("mods", q, limit, offset, slot=slot, rarity=rarity)


@app.get("/bosses")
def list_bosses(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("bosses", q, limit, offset)


@app.get("/locations")
def list_locations(region: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("locations", q, limit, offset, region=region)


@app.get("/recipes")
def list_recipes(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("recipes", q, limit, offset)


@app.get("/materials")
def list_materials(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("materials", q, limit, offset)


@app.get("/scenarios")
def list_scenarios(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("scenarios", q, limit, offset)


@app.get("/quests")
def list_quests(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("quests", q, limit, offset)


@app.get("/events")
def list_events(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("events", q, limit, offset)


@app.get("/creatures")
def list_creatures(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("creatures", q, limit, offset)


@app.get("/npcs")
def list_npcs(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("npcs", q, limit, offset)


@app.get("/plants")
def list_plants(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("plants", q, limit, offset)


@app.get("/fish")
def list_fish(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("fish", q, limit, offset)


@app.get("/animals")
def list_animals(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("animals", q, limit, offset)


@app.get("/flowers")
def list_flowers(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("flowers", q, limit, offset)


# User layer (favorites / notes) — never touches pack DB
@app.get("/user/favorites")
def list_favorites(table: str | None = None):
    conn = get_user_db()
    try:
        if table:
            rows = conn.execute("SELECT * FROM favorites WHERE table_name=?", (table,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM favorites").fetchall()
        return {"favorites": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/user/favorites")
def add_favorite(table: str = Query(...), item_id: str = Query(...), note: str = ""):
    if table not in TABLES:
        raise HTTPException(400, "Unknown table")
    conn = get_user_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO favorites VALUES (?,?,?,?)",
            (table, item_id, note, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"ok": True, "table": table, "item_id": item_id}
    finally:
        conn.close()


@app.delete("/user/favorites")
def remove_favorite(table: str = Query(...), item_id: str = Query(...)):
    conn = get_user_db()
    try:
        conn.execute("DELETE FROM favorites WHERE table_name=? AND item_id=?", (table, item_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/update/check")
def update_check():
    import urllib.request

    local_path = BASE / "version.json"
    local = {}
    if local_path.exists():
        local = json.loads(local_path.read_text(encoding="utf-8"))
    raw = (local.get("github") or {}).get("raw_base") or (
        "https://raw.githubusercontent.com/smus-rgb/once-human-guide/main"
    )
    try:
        req = urllib.request.Request(
            f"{raw}/version.json",
            headers={"User-Agent": f"OnceHumanGuide-API/{API_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            remote = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "local": local, "update_available": False}
    available = (remote.get("data_version") != local.get("data_version")) or (
        remote.get("app_version") != local.get("app_version")
    )
    return {
        "ok": True,
        "update_available": available,
        "local": {
            "app_version": local.get("app_version"),
            "data_version": local.get("data_version"),
            "shell_version": local.get("shell_version"),
        },
        "remote": {
            "app_version": remote.get("app_version"),
            "shell_version": remote.get("shell_version"),
            "data_version": remote.get("data_version"),
            "records": remote.get("records"),
            "released_at": remote.get("released_at"),
            "notes": remote.get("notes"),
        },
    }


@app.post("/update/run")
def update_run(force: bool = False):
    import subprocess
    import sys

    updater = BASE / "updater.py"
    if not updater.exists():
        raise HTTPException(404, "updater.py not found")
    cmd = [sys.executable, str(updater)]
    if force:
        cmd.append("--force")
    try:
        proc = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Update timed out") from exc
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:] if proc.stdout else "",
        "stderr": proc.stderr[-2000:] if proc.stderr else "",
    }


@app.get("/{table}/{item_id}")
def get_item(table: str, item_id: str):
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"{table}/{item_id} not found")
    return rows_to_list([row])[0]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_main:app", host="0.0.0.0", port=8000, reload=False)

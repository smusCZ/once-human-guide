"""Once Human Guide API — pack DB + separate user layer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
if not DB_PATH.exists():
    DB_PATH = BASE.parent / "once_human.db"
USER_DB_PATH = BASE / "once_human_user.db"

def load_meta() -> dict:
    path = BASE / "version.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

META = load_meta()
DATA_VERSION = META.get("data_version", "2026-10-01-v19.1-372")
API_VERSION = META.get("app_version", "5.4.0")
EXPECTED_RECORDS = int(META.get("records") or 372)
MAP_EMBEDS = {
    "thgl": "https://oncehuman.th.gl",
    "mapgenie": "https://mapgenie.io/once-human/maps/nalcott",
}
TABLES = [
    "deviations", "weapons", "armor", "mods", "bosses", "locations",
    "recipes", "materials", "scenarios", "quests", "events", "creatures",
    "npcs", "plants", "fish", "animals", "flowers",
]
USER_KINDS = {"favorite", "inventory", "build", "queue"}

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
    from db_build import ensure_user_db
    ensure_user_db(USER_DB_PATH)
    conn = sqlite3.connect(str(USER_DB_PATH))
    conn.row_factory = sqlite3.Row
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


def fetch_all(table: str, q: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    try:
        if q:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE lower(name) LIKE ? OR lower(coalesce(desc,'')) LIKE ? LIMIT ? OFFSET ?",
                (f"%{q.lower()}%", f"%{q.lower()}%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table} LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        raise HTTPException(500, str(exc)) from exc
    conn.close()
    return rows_to_list(rows)


def fts_query(q: str) -> str:
    parts = []
    for raw in q.replace('"', " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in "-_")
        if token:
            parts.append(token + "*")
    return " OR ".join(parts) or "ohg"


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "Once Human Guide API",
        "api_version": API_VERSION,
        "data_version": DATA_VERSION,
        "tables": TABLES,
        "endpoints": {
            "ui": "/ui",
            "health": "/health",
            "version": "/version",
            "stats": "/stats",
            "search": "/search?q=",
            "integrity": "/integrity",
            "links": "/links/{table}/{id}",
            "user": "/user/{kind}",
            "export": "/export",
            "maps": "/maps",
        },
    }


@app.get("/health")
def health():
    ok = DB_PATH.exists()
    records = None
    if ok:
        conn = get_db()
        try:
            records = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        except sqlite3.Error:
            records = None
        conn.close()
    return {
        "ok": ok and records == EXPECTED_RECORDS,
        "db": str(DB_PATH),
        "user_db": USER_DB_PATH.exists(),
        "records": records,
        "expected": EXPECTED_RECORDS,
        "api_version": API_VERSION,
        "shell": META.get("shell_version"),
    }


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
        row = conn.execute("SELECT version, updated_at FROM data_versions WHERE table_name='all'").fetchone()
        ver = row["version"] if row else DATA_VERSION
        updated = row["updated_at"] if row else None
        schema = conn.execute("SELECT version FROM data_versions WHERE table_name='schema'").fetchone()
    except Exception:
        ver, updated, schema = DATA_VERSION, None, None
    finally:
        conn.close()
    return {
        "data_version": ver,
        "api_version": API_VERSION,
        "shell_version": META.get("shell_version"),
        "schema": schema["version"] if schema else None,
        "updated_at": updated,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "maps": MAP_EMBEDS,
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
    total = sum(counts.values())
    if total != EXPECTED_RECORDS:
        issues.append({"expected_records": EXPECTED_RECORDS, "actual": total})
    try:
        unresolved = conn.execute(
            "SELECT issue, COUNT(*) n FROM data_issues GROUP BY issue"
        ).fetchall()
        issue_counts = {r["issue"]: r["n"] for r in unresolved}
    except sqlite3.Error:
        issue_counts = {}
    conn.close()
    return {
        "ok": quick == "ok" and total == EXPECTED_RECORDS and not any("error" in i for i in issues),
        "quick_check": quick,
        "counts": counts,
        "issues": issues,
        "derived_issues": issue_counts,
        "expected_records": EXPECTED_RECORDS,
    }


@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    table: str | None = None,
):
    if table and table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    match = fts_query(q)
    try:
        sql = """SELECT table_name, id, name, blob
                 FROM entities_fts WHERE entities_fts MATCH ?"""
        args: list = [match]
        if table:
            sql += " AND table_name = ?"
            args.append(table)
        sql += " LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        mode = "fts"
    except sqlite3.Error:
        like = f"%{q.lower()}%"
        sql = """SELECT table_name, id, name, blob FROM entities
                 WHERE (lower(name) LIKE ? OR lower(coalesce(name_fold,'')) LIKE ? OR lower(blob) LIKE ?)"""
        args = [like, like, like]
        if table:
            sql += " AND table_name = ?"
            args.append(table)
        sql += " LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        mode = "like"
    conn.close()
    results = [
        {"table": r["table_name"], "id": r["id"], "name": r["name"], "snippet": (r["blob"] or "")[:180]}
        for r in rows
    ]
    return {"q": q, "mode": mode, "count": len(results), "results": results}


@app.get("/links/{table}/{item_id}")
def links(table: str, item_id: str):
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT dst_table AS table_name, dst_id AS id, relation, score, 'out' AS dir
               FROM links WHERE src_table=? AND src_id=?
               UNION
               SELECT src_table, src_id, relation, score, 'in' FROM links
               WHERE dst_table=? AND dst_id=?""",
            (table, item_id, table, item_id),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    conn.close()
    return {"table": table, "id": item_id, "links": [dict(r) for r in rows]}


@app.get("/user/{kind}")
def user_list(kind: str):
    if kind not in USER_KINDS:
        raise HTTPException(404, "Unknown user kind")
    conn = get_user_db()
    rows = conn.execute(
        "SELECT table_name, item_id, payload, updated_at FROM user_items WHERE kind=? ORDER BY updated_at DESC",
        (kind,),
    ).fetchall()
    conn.close()
    return {"kind": kind, "items": [dict(r) for r in rows]}


@app.put("/user/{kind}")
def user_put(kind: str, body: dict):
    if kind not in USER_KINDS:
        raise HTTPException(404, "Unknown user kind")
    table = body.get("table")
    item_id = body.get("id")
    if table not in TABLES or not item_id:
        raise HTTPException(400, "table and id required")
    conn = get_user_db()
    now = datetime.now(timezone.utc).isoformat()
    if body.get("remove"):
        conn.execute(
            "DELETE FROM user_items WHERE kind=? AND table_name=? AND item_id=?",
            (kind, table, item_id),
        )
    else:
        conn.execute(
            """INSERT INTO user_items VALUES (?,?,?,?,?)
               ON CONFLICT(kind, table_name, item_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
            (kind, table, item_id, json.dumps(body.get("payload") or {}, ensure_ascii=False), now),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "kind": kind, "table": table, "id": item_id}


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


def _list(table: str, q: str | None = None, limit: int = 500, offset: int = 0):
    return fetch_all(table, q, limit, offset)


@app.get("/deviations")
def list_deviations(type: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0):
    items = _list("deviations", q, limit, offset)
    if type:
        items = [i for i in items if (i.get("type") or "").lower() == type.lower()]
    return items


@app.get("/weapons")
def list_weapons(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("weapons", q, limit, offset)


@app.get("/armor")
def list_armor(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("armor", q, limit, offset)


@app.get("/mods")
def list_mods(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("mods", q, limit, offset)


@app.get("/bosses")
def list_bosses(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("bosses", q, limit, offset)


@app.get("/locations")
def list_locations(q: str | None = None, limit: int = 500, offset: int = 0):
    return _list("locations", q, limit, offset)


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


@app.get("/update/check")
def update_check():
    import urllib.request
    local = META
    raw = (local.get("github") or {}).get("raw_base") or (
        "https://raw.githubusercontent.com/smus-rgb/once-human-guide/main"
    )
    try:
        req = urllib.request.Request(
            f"{raw}/version.json",
            headers={"User-Agent": "OnceHumanGuide-API/5.7"},
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
def update_run(force: bool = False, x_ohg_token: str | None = Header(default=None)):
    import subprocess
    import sys
    expected = os.environ.get("OHG_UPDATE_TOKEN", "")
    if not expected or x_ohg_token != expected:
        raise HTTPException(403, "Set OHG_UPDATE_TOKEN and send X-OHG-Token")
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
    uvicorn.run("api_main:app", host="127.0.0.1", port=8000, reload=False)

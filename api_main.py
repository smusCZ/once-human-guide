"""Once Human Guide API 5.5 — FastAPI + SQLite + FTS + user layer."""
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
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "once_human.db"
if not DB_PATH.exists():
    DB_PATH = BASE.parent / "once_human.db"
USER_DB = BASE / "once_human_user.db"

DATA_VERSION = "2026-10-07-v19.2-372"
API_VERSION = "5.5.0"
MAP_EMBEDS = {
    "thgl": "https://oncehuman.th.gl",
    "mapgenie": "https://mapgenie.io/once-human/maps/nalcott",
}
TABLES = [
    "deviations", "weapons", "armor", "mods", "bosses", "locations",
    "recipes", "materials", "scenarios", "quests", "events", "creatures",
    "npcs", "plants", "fish", "animals", "flowers",
]

app = FastAPI(title="Once Human Guide API", version=API_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if (BASE / "modules").is_dir():
    app.mount("/modules", StaticFiles(directory=BASE / "modules"), name="modules")


class FavoriteIn(BaseModel):
    table: str
    id: str
    note: str | None = None


def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, f"Database not found at {DB_PATH}. Run python db_build.py")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_user_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(USER_DB))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS favorites (
            table_name TEXT NOT NULL, id TEXT NOT NULL, note TEXT,
            created_at TEXT NOT NULL, PRIMARY KEY (table_name, id)
        )"""
    )
    conn.commit()
    return conn


def rows_to_list(rows) -> list[dict]:
    items = [dict(r) for r in rows]
    for item in items:
        for key in ("tags", "ingredients", "drops", "locations", "pieces"):
            if key in item and isinstance(item[key], str):
                try:
                    item[key] = json.loads(item[key] or "[]")
                except Exception:
                    pass
    return items


def fts_query(q: str) -> str:
    tokens = re.findall(r"[\w]+", q, flags=re.UNICODE)[:8]
    return " AND ".join('"' + token + '"*' for token in tokens)


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


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "Once Human Guide API",
        "api_version": API_VERSION,
        "data_version": DATA_VERSION,
        "tables": TABLES,
        "endpoints": {
            "ui": "/ui", "health": "/health", "search": "/search?q=",
            "catalog": "/catalog", "suggest": "/suggest?q=",
            "compare": "/compare", "favorites": "/user/favorites",
            "integrity": "/integrity",
        },
    }


@app.get("/health")
def health():
    return {"ok": DB_PATH.exists(), "db": str(DB_PATH), "user_db": str(USER_DB), "api_version": API_VERSION}


@app.get("/ui")
def serve_ui():
    for name in ("once_human_guide_v19.html", "once_human_guide_v18.html", "once_human_guide_ui_v4.html", "once_human_guide_app.html"):
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


@app.get("/stats")
def stats():
    conn = get_db()
    out, total = {}, 0
    for table in TABLES:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            n = 0
        out[table] = n
        total += n
    conn.close()
    out["total"] = total
    out["data_version"] = DATA_VERSION
    return out


@app.get("/integrity")
def integrity():
    conn = get_db()
    issues, counts = [], {}
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
    extra = {}
    for table in ("unresolved_refs", "duplicate_names", "links"):
        try:
            extra[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            extra[table] = None
    quick = conn.execute("PRAGMA quick_check").fetchone()[0]
    conn.close()
    return {"ok": quick == "ok" and not issues, "quick_check": quick, "counts": counts, "audit": extra, "issues": issues, "expected_records": 372}


@app.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=200)):
    conn = get_db()
    match = fts_query(q)
    mode, rows = "fts", []
    if match:
        try:
            rows = conn.execute(
                "SELECT table_name, id, name, blob FROM entities_fts WHERE entities_fts MATCH ? LIMIT ?",
                (match, limit),
            ).fetchall()
        except sqlite3.Error:
            mode = "like"
    if not rows:
        mode = "like"
        rows = conn.execute(
            "SELECT table_name, id, name, blob FROM entities WHERE lower(name) LIKE ? OR lower(blob) LIKE ? LIMIT ?",
            (f"%{q.lower()}%", f"%{q.lower()}%", limit),
        ).fetchall()
    conn.close()
    results = [{"table": r["table_name"], "id": r["id"], "name": r["name"], "snippet": (r["blob"] or "")[:180]} for r in rows]
    return {"q": q, "mode": mode, "count": len(results), "results": results}


@app.get("/suggest")
def suggest(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=20)):
    conn = get_db()
    rows = conn.execute(
        "SELECT table_name, id, name FROM entities WHERE lower(name) LIKE ? ORDER BY length(name) LIMIT ?",
        (f"{q.lower()}%", limit),
    ).fetchall()
    conn.close()
    return {"q": q, "results": [dict(r) for r in rows]}


@app.get("/catalog")
def catalog(
    table: str | None = None,
    kind: str | None = None,
    rarity: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if table and table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    where, args = ["1=1"], []
    if table:
        where.append("table_name=?")
        args.append(table)
    if kind:
        where.append("lower(kind)=?")
        args.append(kind.lower())
    if rarity:
        where.append("lower(rarity)=?")
        args.append(rarity.lower())
    if q:
        where.append("lower(name) LIKE ?")
        args.append(f"%{q.lower()}%")
    conn = get_db()
    rows = conn.execute(
        f"SELECT table_name, id, name, kind, rarity, region FROM entities WHERE {' AND '.join(where)} LIMIT ? OFFSET ?",
        (*args, limit, offset),
    ).fetchall()
    conn.close()
    return {"count": len(rows), "results": [dict(r) for r in rows]}


@app.get("/compare")
def compare(a: str = Query(...), b: str = Query(...)):
    def parse(token: str) -> tuple[str, str]:
        if ":" not in token:
            raise HTTPException(400, "Use table:id")
        table, item_id = token.split(":", 1)
        if table not in TABLES:
            raise HTTPException(404, table)
        return table, item_id

    left_t, left_id = parse(a)
    right_t, right_id = parse(b)
    conn = get_db()
    left = conn.execute(f"SELECT * FROM {left_t} WHERE id=?", (left_id,)).fetchone()
    right = conn.execute(f"SELECT * FROM {right_t} WHERE id=?", (right_id,)).fetchone()
    conn.close()
    if not left or not right:
        raise HTTPException(404, "Item missing")
    ld, rd = dict(left), dict(right)
    diffs = [k for k in sorted(set(ld) | set(rd)) if ld.get(k) != rd.get(k)]
    return {"a": ld, "b": rd, "diff_keys": diffs}


@app.get("/links/{table}/{item_id}")
def links(table: str, item_id: str):
    if table not in TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT dst_table, dst_id, relation, score FROM links WHERE src_table=? AND src_id=?
               UNION SELECT src_table, src_id, relation, score FROM links WHERE dst_table=? AND dst_id=?""",
            (table, item_id, table, item_id),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    conn.close()
    return {"table": table, "id": item_id, "links": [dict(r) for r in rows]}


@app.get("/user/favorites")
def list_favorites():
    conn = get_user_db()
    rows = conn.execute("SELECT table_name, id, note, created_at FROM favorites ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"favorites": [dict(r) for r in rows]}


@app.post("/user/favorites")
def add_favorite(body: FavoriteIn):
    if body.table not in TABLES:
        raise HTTPException(404, body.table)
    conn = get_user_db()
    conn.execute(
        "INSERT OR REPLACE INTO favorites VALUES (?,?,?,?)",
        (body.table, body.id, body.note, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/user/favorites/{table}/{item_id}")
def remove_favorite(table: str, item_id: str):
    conn = get_user_db()
    conn.execute("DELETE FROM favorites WHERE table_name=? AND id=?", (table, item_id))
    conn.commit()
    conn.close()
    return {"ok": True}


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

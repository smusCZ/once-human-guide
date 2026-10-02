import json
from pathlib import Path

import db_build


def test_pack_count_and_links(tmp_path, monkeypatch):
    monkeypatch.setattr(db_build, "BASE", Path(db_build.__file__).resolve().parent)
    out = db_build.build(tmp_path / "once_human.db")
    assert out["records"] == 372
    assert out["dupes"] == 0
    assert out["links"] > 0
    assert Path(out["user_db"]).exists()


def test_user_db_survives(tmp_path):
    path = tmp_path / "user.db"
    db_build.ensure_user_db(path)
    db_build.ensure_user_db(path)
    assert path.exists()

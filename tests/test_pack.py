"""Pack build must keep the published entity count."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db_build


def test_pack_count_and_user_db_separated(tmp_path, monkeypatch):
    monkeypatch.setattr(db_build, "BASE", ROOT)
    monkeypatch.setattr(db_build, "USER_DB_PATH", tmp_path / "once_human_user.db")
    report = db_build.build(tmp_path / "once_human.db")
    assert report["records"] == 372
    assert report["ok"] is True
    assert report["links"] > 0
    assert (tmp_path / "once_human_user.db").exists()
    assert not (tmp_path / "once_human.db").read_bytes().count(b"user_items")

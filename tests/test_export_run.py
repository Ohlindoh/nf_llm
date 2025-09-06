from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from nf_llm.api.main import app

client = TestClient(app)


SLOTS = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
POS_MAP = {
    "QB": "QB",
    "RB1": "RB",
    "RB2": "RB",
    "WR1": "WR",
    "WR2": "WR",
    "WR3": "WR",
    "TE": "TE",
    "FLEX": "RB",
    "DST": "DST",
}


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE optimizer_lineups (lineup_id INT, run_id INT, slate_id TEXT)"
    )
    con.execute(
        """
        CREATE TABLE optimizer_lineup_players (
            lineup_id INT,
            slot TEXT,
            player_id INT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE salaries (
            slate_id TEXT,
            player_id INT,
            dk_player_id TEXT,
            pos TEXT
        )
        """
    )
    return con, db_path


def test_export_run_dk_csv_success(tmp_path: Path, monkeypatch):
    con, db_path = _setup_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db_path}")

    run_id = 1
    slate = "SLATE1"
    for lid in [1, 2, 3]:
        con.execute(
            "INSERT INTO optimizer_lineups VALUES (?, ?, ?)", [lid, run_id, slate]
        )

    for slot, pid in zip(SLOTS, range(1, 10), strict=False):
        con.execute(
            "INSERT INTO optimizer_lineup_players VALUES (1, ?, ?)", [slot, pid]
        )
    for slot, pid in zip(SLOTS, range(11, 20), strict=False):
        con.execute(
            "INSERT INTO optimizer_lineup_players VALUES (2, ?, ?)", [slot, pid]
        )
    for slot, pid in zip(SLOTS, range(21, 30), strict=False):
        con.execute(
            "INSERT INTO optimizer_lineup_players VALUES (3, ?, ?)", [slot, pid]
        )

    for slot, pid in zip(
        SLOTS * 3,
        list(range(1, 10)) + list(range(11, 20)) + list(range(21, 30)),
        strict=False,
    ):
        pos = POS_MAP[slot]
        con.execute(
            "INSERT INTO salaries VALUES (?, ?, ?, ?)",
            [slate, pid, f"{pid+1000}", pos],
        )
        if slot == "FLEX":
            # duplicate FLEX row should be ignored in favour of positional row
            con.execute(
                "INSERT INTO salaries VALUES (?, ?, ?, 'FLEX')",
                [slate, pid, f"{pid+2000}"],
            )
    con.close()

    resp = client.get(f"/optimizer_runs/{run_id}/export/dk_csv")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/csv")
    assert (
        resp.headers["content-disposition"]
        == 'attachment; filename="SLATE1_NFL_CLASSIC.csv"'
    )

    lines = [ln for ln in resp.text.strip().split("\n") if ln]
    assert lines[0] == "QB,RB,RB,WR,WR,WR,TE,FLEX,DST"
    assert len(lines) == 4
    assert lines[1] == "1001,1002,1003,1004,1005,1006,1007,1008,1009"
    assert lines[2] == "1011,1012,1013,1014,1015,1016,1017,1018,1019"
    assert lines[3] == "1021,1022,1023,1024,1025,1026,1027,1028,1029"


def test_export_run_dk_csv_missing_player(tmp_path: Path, monkeypatch):
    con, db_path = _setup_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db_path}")

    run_id = 2
    slate = "SLATE1"
    con.execute(
        "INSERT INTO optimizer_lineups VALUES (1, ?, ?)", [run_id, slate]
    )
    for slot, pid in zip(SLOTS, range(1, 10), strict=False):
        con.execute(
            "INSERT INTO optimizer_lineup_players VALUES (1, ?, ?)", [slot, pid]
        )
    for slot, pid in zip(SLOTS, range(1, 10), strict=False):
        if pid == 3:
            continue  # omit salary mapping for player 3
        pos = POS_MAP[slot]
        con.execute(
            "INSERT INTO salaries VALUES (?, ?, ?, ?)",
            [slate, pid, f"{pid+1000}", pos],
        )
    con.close()

    resp = client.get(f"/optimizer_runs/{run_id}/export/dk_csv")
    assert resp.status_code == 400
    assert "3" in resp.json()["detail"]


def test_export_run_dk_csv_mixed_slate(tmp_path: Path, monkeypatch):
    con, db_path = _setup_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db_path}")

    run_id = 3
    con.execute(
        "INSERT INTO optimizer_lineups VALUES (1, ?, 'S1')", [run_id]
    )
    con.execute(
        "INSERT INTO optimizer_lineups VALUES (2, ?, 'S2')", [run_id]
    )
    con.close()

    resp = client.get(f"/optimizer_runs/{run_id}/export/dk_csv")
    assert resp.status_code == 400
    assert "multiple slates" in resp.json()["detail"].lower()


def test_export_run_dk_csv_bad_slots(tmp_path: Path, monkeypatch):
    con, db_path = _setup_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db_path}")

    run_id = 4
    slate = "SLATE1"
    con.execute("INSERT INTO optimizer_lineups VALUES (1, ?, ?)", [run_id, slate])
    # missing WR3, extra K slot
    slots = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "DST", "K"]
    for slot, pid in zip(slots, range(1, 10), strict=False):
        con.execute(
            "INSERT INTO optimizer_lineup_players VALUES (1, ?, ?)", [slot, pid]
        )
        pos = POS_MAP.get(slot, "DST")
        con.execute(
            "INSERT INTO salaries VALUES (?, ?, ?, ?)",
            [slate, pid, f"{pid+1000}", pos],
        )
    con.close()

    resp = client.get(f"/optimizer_runs/{run_id}/export/dk_csv")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "WR3" in detail
    assert "K" in detail

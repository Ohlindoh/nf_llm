# tests/test_api.py
from pathlib import Path

from fastapi.testclient import TestClient

from nf_llm.api.main import app  # import the FastAPI instance

client = TestClient(app)


def test_optimise_happy_path(tmp_path: Path):
    # --- arrange ---
    # point to a *real* CSV in your repo; here we copy one into tmp_path
    sample_csv = tmp_path / "DK_MAIN_2025W01_raw.csv"
    sample_csv.write_text(
        """player_name,player_position_id,team,salary,projected_points
    C.J. Stroud,QB,HOU,7000,22.4
    Justin Herbert,QB,LAC,7500,23.8
    Bijan Robinson,RB,ATL,7000,20.1
    Jerome Ford,RB,CLE,5500,14.6
    Jaylen Warren,RB,PIT,5000,13.8
    Christian McCaffrey,RB,SF,9200,24.5
    Stefon Diggs,WR,BUF,8000,20.7
    Chris Godwin,WR,TB,6500,16.4
    George Pickens,WR,PIT,6000,15.2
    Zay Jones,WR,JAX,4800,12.3
    Michael Wilson,WR,ARI,3900,9.8
    CeeDee Lamb,WR,DAL,7700,21.0
    Mark Andrews,TE,BAL,6300,15.0
    Tyler Conklin,TE,NYJ,3300,9.6
    Cardinals,DST,ARI,2500,6.8
""",
        encoding="utf-8",
    )

    payload = {
        "csv_path": str(sample_csv),
        "constraints": {"num_lineups": 1},
    }

    # --- act ---
    resp = client.post("/optimise", json=payload)

    # --- assert ---
    assert resp.status_code == 200
    data = resp.json()
    assert data["slate_id"] == "DK_MAIN_2025W01"
    assert "lineups" in data and isinstance(data["lineups"], list)
    assert len(data["lineups"]) == 1
    # each lineup should be a dict keyed by positions
    assert isinstance(data["lineups"][0], dict)


def test_export_dk_csv(tmp_path: Path, monkeypatch):
    slate_id = "DK_MAIN_2025W01"
    salaries_dir = tmp_path / "dk_salaries"
    salaries_dir.mkdir()
    salary_file = salaries_dir / f"{slate_id}_raw.csv"
    salary_file.write_text(
        """playerId,playerDkId,draftableId
1,123,100
2,234,101
3,345,102
4,456,103
5,567,104
6,678,105
7,789,106
8,890,107
9,901,108
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DK_SALARIES_DIR", str(salaries_dir))

    payload = {
        "slate_id": slate_id,
        "lineups": [
            ["123", "234", "345", "456", "567", "678", "789", "890", "901"],
            ["123", "234", "999", "456", "567", "678", "789", "890", "901"],
            ["123", "234", "345", "456", "567", "678", "789", "890"],
        ],
    }

    resp = client.post("/export/dk_csv", json=payload)
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/csv")

    lines = [ln for ln in resp.text.strip().split("\n") if ln]
    assert lines[0] == "QB,RB,RB,WR,WR,WR,TE,FLEX,DST"
    assert len(lines) == 2  # header + 1 valid lineup
    assert lines[1] == "123,234,345,456,567,678,789,890,901"
    assert resp.headers["X-Invalid-Lineups"] == "2,3"

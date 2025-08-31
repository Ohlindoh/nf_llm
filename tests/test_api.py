# tests/test_api.py
from pathlib import Path

from fastapi.testclient import TestClient

from nf_llm.api.main import app  # import the FastAPI instance

client = TestClient(app)


def test_optimise_happy_path(tmp_path: Path):
    # --- arrange ---
    # point to a *real* CSV in your repo; here we copy one into tmp_path
    sample_csv = tmp_path / "players.csv"
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
        "slate_id": "DK-NFL-2025-Week01",
        "constraints": {"num_lineups": 1},
    }

    # --- act ---
    resp = client.post("/optimise", json=payload)

    # --- assert ---
    assert resp.status_code == 200
    data = resp.json()
    assert "lineups" in data and isinstance(data["lineups"], list)
    assert len(data["lineups"]) == 1
    # each lineup should be a dict keyed by positions
    assert isinstance(data["lineups"][0], dict)

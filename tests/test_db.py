from nf_llm.db import get_conn

def test_schema_exists():
    con = get_conn()
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert "dim_player" in tables

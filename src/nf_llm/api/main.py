import logging
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from nf_llm.service import build_lineups, export_dk_csv, export_run_dk_csv

app = FastAPI(title="NF-LLM API", version="0.1.0")


class LineupRequest(BaseModel):
    csv_path: str = Field(..., description="Path to player CSV")
    slate_id: str = Field(..., description="Contest or slate identifier")
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Optimizer constraints (num_lineups, max_exposure, etc.)",
    )


class LineupResponse(BaseModel):
    lineups: list[dict[str, Any]]


class UndervaluedPlayersRequest(BaseModel):
    csv_path: str = Field(..., description="Path to player CSV")
    top_n: int = Field(default=5, description="Number of top players per position")


class UndervaluedPlayersResponse(BaseModel):
    players: dict[str, list[dict[str, Any]]]


class DKCSVRequest(BaseModel):
    slate_id: str = Field(..., description="DraftKings slate identifier")
    lineups: list[list[str]] = Field(..., description="List of lineups to export")


@app.on_event("startup")
def on_startup():
    pass


@app.post("/optimise", response_model=LineupResponse)
def optimise(req: LineupRequest):
    """
    Thin HTTP wrapper that delegates to the pure function.
    """
    try:
        lineups = build_lineups(
            csv_path=req.csv_path,
            slate_id=req.slate_id,
            constraints=req.constraints,
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        logging.error("Optimiser crashed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal optimiser error") from err

    return {"lineups": lineups}


@app.post("/undervalued-players", response_model=UndervaluedPlayersResponse)
def get_undervalued_players_endpoint(req: UndervaluedPlayersRequest):
    """
    Get most undervalued players by position.
    """
    try:
        from nf_llm.service import get_undervalued_players_data

        players = get_undervalued_players_data(req.csv_path, req.top_n)
        return {"players": players}
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except Exception as err:
        logging.error(
            "Undervalued players endpoint crashed:\n%s", traceback.format_exc()
        )
        raise HTTPException(
            status_code=500, detail="Internal error getting undervalued players"
        ) from err


@app.post("/export/dk_csv", deprecated=True)
def export_dk_csv_endpoint(req: DKCSVRequest):
    """Validate lineups and return a DraftKings upload CSV.

    The response body is the CSV content. If any lineups fail validation, their
    1-based indices are exposed in the ``X-Invalid-Lineups`` header.
    """

    try:
        csv_content, invalid = export_dk_csv(req.slate_id, req.lineups)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except Exception as err:  # pragma: no cover - unexpected errors
        logging.error("DK CSV export crashed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal DK CSV error") from err

    headers = {}
    if invalid:
        headers["X-Invalid-Lineups"] = ",".join(str(i) for i in invalid)

    return Response(content=csv_content, media_type="text/csv", headers=headers)


@app.get("/optimizer_runs/{run_id}/export/dk_csv")
def export_run_dk_csv_endpoint(run_id: int):
    """Return a DraftKings CSV for a stored optimiser run."""

    try:
        csv_content, slate_id = export_run_dk_csv(run_id)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:  # pragma: no cover - unexpected errors
        logging.error("DK CSV export crashed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal DK CSV error") from err

    headers = {
        "Content-Disposition": f"attachment; filename=\"{slate_id}_NFL_CLASSIC.csv\""
    }

    return Response(content=csv_content, media_type="text/csv", headers=headers)


@app.get("/health")
def health():
    return {"status": "ok"}

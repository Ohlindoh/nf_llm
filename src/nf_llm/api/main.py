from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging
from logging import error
import traceback

from nf_llm.service import build_lineups, compute_weekly_plan

app = FastAPI(title="NF-LLM API", version="0.1.0")


class LineupRequest(BaseModel):
    csv_path: str = Field(..., description="Path to player CSV")
    slate_id: str = Field(..., description="Contest or slate identifier")
    constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optimizer constraints (num_lineups, max_exposure, etc.)",
    )


class LineupResponse(BaseModel):
    lineups: List[Dict[str, Any]]


class UndervaluedPlayersRequest(BaseModel):
    csv_path: str = Field(..., description="Path to player CSV")
    top_n: int = Field(default=5, description="Number of top players per position")


class UndervaluedPlayersResponse(BaseModel):
    players: Dict[str, List[Dict[str, Any]]]


class WeeklyPlanRequest(BaseModel):
    league_id: str
    year: int
    espn_s2: str
    swid: str
    preferences_text: Optional[str] = None
    max_acquisitions: int = 2
    positions_to_fill: Optional[List[str]] = None


class WeeklyPlanResponse(BaseModel):
    meta: Dict[str, Any]
    league_profile: Dict[str, Any]
    start_sit: Dict[str, Any]
    acquisitions: List[Dict[str, Any]]
    notes: List[str]


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


@app.post("/espn/weekly_plan", response_model=WeeklyPlanResponse)
def espn_weekly_plan(req: WeeklyPlanRequest):
    """Generate weekly plan based on ESPN league data."""
    try:
        plan = compute_weekly_plan(
            league_id=req.league_id,
            year=req.year,
            espn_s2=req.espn_s2,
            swid=req.swid,
            preferences_text=req.preferences_text,
            max_acquisitions=req.max_acquisitions,
            positions_to_fill=req.positions_to_fill,
        )
        return plan
    except RuntimeError as err:
        raise HTTPException(status_code=501, detail=str(err))
    except Exception as err:
        logging.error("Weekly plan endpoint crashed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=500, detail="Failed to compute weekly plan"
        ) from err


@app.get("/health")
def health():
    return {"status": "ok"}

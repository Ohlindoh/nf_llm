# src/nf_llm/api/main.py
from fastapi import FastAPI
from nf_llm.db import init_db   # runs once to ensure tables exist
from pydantic import BaseModel

init_db()

app = FastAPI(title="nf-llm API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

class LineupIn(BaseModel):
    name: str

class LineupOut(LineupIn):
    id: int
    salary: float
    projected: float

# hard-coded example lineup – no DB, no optimiser yet
DUMMY_RESULT = {
    "id": 1,
    "salary": 49900.0,
    "projected": 185.3,
}

@app.post("/optimise", response_model=LineupOut)
def optimise(payload: LineupIn):
    """Return a fixed lineup just to prove the plumbing works."""
    return {**payload.model_dump(), **DUMMY_RESULT}

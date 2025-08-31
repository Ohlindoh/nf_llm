# NF LLM

Fantasy football data collection and lineup optimization using LLMs.

## Setup

Install [uv](https://github.com/astral-sh/uv):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install dependencies:
```bash
uv sync
```

The weekly plan feature depends on the community `espn-api` package. If it's not
present, install it with:
```bash
uv add espn-api
```

## Usage

**Collect data:**
```bash
uv run python -m nf_llm.collect --dk_contest_type Main
```

**Run the app:**
```bash
docker-compose up --build
```

Access the UI at http://localhost:8501

### Weekly Plan (ESPN)

1. Open the app in your browser.
2. Locate the **Weekly Plan (ESPN)** panel.
3. Enter your `league_id`, `year`, `espn_s2`, and `swid` cookies.
4. Optionally provide natural language preferences, a maximum number of acquisitions, or a comma-separated list of positions to fill.
5. Click **Compute Weekly Plan** to call the stateless `POST /espn/weekly_plan` API and view start/sit recommendations and suggested waiver pickups.

## Development

**Run tests:**
```bash
uv run pytest
```

**Code quality:**
```bash
uv run black .
uv run ruff check .
```

**Add dependencies:**
```bash
uv add package-name
```

## Environment

Set `OPENAI_API_KEY` for LLM features.

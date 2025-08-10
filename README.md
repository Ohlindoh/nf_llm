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

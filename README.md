# NF LLM

This project contains utilities for collecting fantasy football data and generating optimized lineups using large language models.

## Prerequisites

- Python 3.11+ 
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer and resolver

Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Quick Start

1. **Install dependencies**
   ```bash
   uv sync
   ```
   This creates a virtual environment and installs all dependencies defined in `pyproject.toml`.

2. **Activate the environment** (optional, uv run handles this automatically)
   ```bash
   source .venv/bin/activate  # Linux/Mac
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Run tests**
   ```bash
   uv run pytest
   ```

4. **Initialize the database**
   Apply the schema to create `data/nf_llm.db`:
   ```bash
   uv run python -m nf_llm.cli db init
   ```

5. **Collect data**
   ```bash
   uv run python -m nf_llm.collect --dk_contest_type Main
   ```

6. **Run the lineup optimizer**
   ```bash
   uv run python -m nf_llm.app
   ```
   The optimizer expects an environment variable `OPENAI_API_KEY` for LLM access.

## Development

### Adding Dependencies

Add new dependencies to `pyproject.toml`:
```bash
# Add a new dependency
uv add package-name

# Add a development dependency  
uv add --dev package-name

# Add with version constraints
uv add "package-name>=1.0,<2.0"
```

### Code Quality

Run linting and formatting:
```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/
```

### Docker Development

Build and run with Docker Compose:
```bash
docker-compose up --build
```

This will start:
- PostgreSQL database on port 5432
- API server on port 8000  
- Streamlit UI on port 8501

## Project Structure

For more detailed usage, inspect the source files under `src/nf_llm/`.

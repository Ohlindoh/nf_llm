# NF LLM

This project contains utilities for collecting fantasy football data and generating optimized lineups using large language models.

## Quick start

1. **Install dependencies**
   ```bash
   make install
   ```
   This uses [`uv`](https://github.com/astral-sh/uv) to create a local virtual environment and install the packages defined in `pyproject.toml`.

2. **Run tests**
   ```bash
   pytest
   ```

3. **Initialize the database**
   Apply the schema to create `data/nf_llm.db`:
   ```bash
   PYTHONPATH=src python -m nf_llm.cli db init
   ```
   (If you install the package, you can use `nf-llm db init` instead.)

4. **Collect data**
   ```bash
   python -m nf_llm.collect --dk_contest_type Main
   ```

5. **Run the lineup optimizer**
   ```bash
   python -m nf_llm.app
   ```
   The optimizer expects an environment variable `OPENAI_API_KEY` for LLM access.

For more detailed usage, inspect the source files under `src/nf_llm`.

install:
	uv sync --frozen || (uv pip compile pyproject.toml -o uv.lock && uv sync)

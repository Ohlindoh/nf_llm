lock:
	uv pip compile pyproject.toml -o uv.lock

install:
	uv sync --frozen || (make lock && uv sync)

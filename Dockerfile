# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . /app
RUN uv pip install --system .

EXPOSE 8501
CMD ["streamlit", "run", "src/nf_llm/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
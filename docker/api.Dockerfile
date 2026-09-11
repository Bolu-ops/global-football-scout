FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY gfs_core ./gfs_core
COPY data_pipeline ./data_pipeline
COPY ml ./ml
COPY backend ./backend
COPY scripts ./scripts
COPY database ./database
COPY alembic.ini ./
RUN pip install -e ".[ml,llm]"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]

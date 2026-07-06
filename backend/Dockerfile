FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=postgresql+psycopg://tutor:tutor@db:5432/tutor \
    RAG_UPLOAD_DIR=/data/storage/materials \
    RAG_VECTOR_DIM=1536 \
    RAG_HNSW_EF_SEARCH=40 \
    RAG_EMBEDDING_BASE_URL=https://api.openai.com/v1 \
    RAG_EMBEDDING_MODEL=text-embedding-3-small \
    ALLOW_GLOBAL_LLM_FALLBACK=True

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/storage/materials \
    && chown -R app:app /app /data

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN chown -R app:app /app

USER app

EXPOSE 8001

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]

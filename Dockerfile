FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=4100 \
    CORPUS_PATH="research_dataset/corpus_chunks_complete.jsonl"

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY panchakarma_evidence ./panchakarma_evidence

RUN pip install --no-cache-dir .

# Copy corpus, schemas, and registries (source PDFs are excluded from docker images)
COPY research_dataset/corpus_chunks.jsonl ./research_dataset/corpus_chunks.jsonl
COPY research_dataset/corpus_chunks_complete.jsonl ./research_dataset/corpus_chunks_complete.jsonl
COPY research_dataset/synthetic_demo_corpus.jsonl ./research_dataset/synthetic_demo_corpus.jsonl
COPY research_dataset/source_registry.csv ./research_dataset/source_registry.csv
COPY research_dataset/corpus_schema.json ./research_dataset/corpus_schema.json

# Create directory for SQLite fallback data
RUN mkdir -p /app/data

EXPOSE 4100

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "panchakarma_evidence"]

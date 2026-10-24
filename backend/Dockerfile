# Built from the repository root: the backend imports ml/, reads schema/thresholds.json and
# serves data/snapshots/ when no fresh report exists; scripts/seed.py loads the roof snapshot
# from there and the demo roofs.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY ml/requirements.txt ml/requirements.txt
RUN pip install -r backend/requirements.txt -r ml/requirements.txt

COPY schema schema
COPY ml ml
COPY data/snapshots data/snapshots
COPY scripts/seed.py scripts/import_roofs.py scripts/
COPY backend backend

WORKDIR /app/backend
EXPOSE 8000
# Migrations and the demo seed run on every start; both are idempotent. Earth Engine
# steps are not run: the evidence endpoints fall back to data/snapshots/.
CMD ["sh", "-c", "alembic upgrade head && python ../scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

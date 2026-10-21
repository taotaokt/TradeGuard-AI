FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY ml ./ml
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN addgroup --system tradeguard && adduser --system --ingroup tradeguard tradeguard \
    && mkdir -p /app/uploads \
    && chown -R tradeguard:tradeguard /app/uploads

USER tradeguard

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]

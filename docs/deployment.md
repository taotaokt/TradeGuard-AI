# Deployment guide

TradeGuard AI can run locally with SQLite or as a two-container application with PostgreSQL. The production Compose file is a deployment reference for a portfolio demonstration, not a complete regulated-production platform.

## Local demo

```bash
cp .env.example .env
python3 -m pip install -e '.[dev]'
python3 -m alembic upgrade head
python3 scripts/seed_demo.py
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>. The API documentation remains available at <http://localhost:8000/docs>.

## Container deployment

Set secrets in the shell or a protected environment file that is not committed:

```bash
export POSTGRES_PASSWORD='replace-with-a-strong-random-password'
export SECRET_KEY='replace-with-at-least-32-random-bytes'
export INITIAL_ADMIN_EMAIL='your-admin@example.com'
export INITIAL_ADMIN_PASSWORD='replace-with-a-unique-admin-password'
export ALLOWED_ORIGINS='https://your-host.example'
docker compose -f docker-compose.production.yml up --build -d
```

The API container runs as an unprivileged user, applies Alembic migrations at startup, exposes a health check, and stores uploads and PostgreSQL data in named volumes. Terminate TLS at a trusted reverse proxy or managed platform.

## Backup and restore

Create an encrypted, access-controlled database backup:

```bash
docker compose -f docker-compose.production.yml exec -T db pg_dump -U tradeguard -Fc tradeguard > tradeguard.backup
```

Restore into an empty database after testing the procedure in a non-production environment:

```bash
docker compose -f docker-compose.production.yml exec -T db pg_restore -U tradeguard -d tradeguard --clean --if-exists < tradeguard.backup
```

Back up the `tradeguard_uploads` volume separately. A database backup alone does not contain uploaded evidence.

## Production gaps

Before real business use, add managed secrets, TLS, encrypted backups, object storage with malware scanning, centralized logs, rate limiting, monitoring and alerting, a documented retention policy, disaster-recovery testing, and an independent security review. Replace the synthetic model with a governed validation process before using real outcomes.

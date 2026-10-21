.PHONY: install migrate run test clean

install:
	python3 -m pip install -e '.[dev]'

migrate:
	python3 -m alembic upgrade head

run:
	python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	python3 -m pytest

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

import os
import shutil
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_tradeguard.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
os.environ["INITIAL_ADMIN_PASSWORD"] = "test-password"
os.environ["UPLOAD_DIR"] = "./test_uploads"

import pytest
from fastapi.testclient import TestClient

from backend.app.db import Base, engine
from backend.app.main import app


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Path("test_tradeguard.db").unlink(missing_ok=True)
    shutil.rmtree("test_uploads", ignore_errors=True)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-password"}
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer {}".format(response.json()["access_token"])}

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


def test_health_endpoint() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


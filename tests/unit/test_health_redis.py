"""Check Redis health through the configured URL."""

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.health import router
from core.config import settings
from core.database import get_db

pytestmark = pytest.mark.unit


class FailingDB:
    async def execute(self, query):
        raise RuntimeError("Separate database health failure")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    async def get_failing_db():
        yield FailingDB()

    app.dependency_overrides[get_db] = get_failing_db
    return TestClient(app)


def test_reachable_redis_is_healthy_even_when_postgres_fails(client, monkeypatch):
    class ReachableRedis:
        def ping(self):
            return True

    calls = []

    def connect(url, **kwargs):
        calls.append((url, kwargs))
        return ReachableRedis()

    monkeypatch.setattr(redis.Redis, "from_url", connect)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["dependencies"]["redis"] == "healthy"
    assert response.json()["detail"]["dependencies"]["postgres"] == "unhealthy"
    assert calls == [(settings.redis_url, {"decode_responses": True})]


def test_unreachable_redis_is_unhealthy(client, monkeypatch):
    class UnreachableRedis:
        def ping(self):
            raise redis.exceptions.ConnectionError("Redis unavailable")

    monkeypatch.setattr(redis.Redis, "from_url", lambda url, **kwargs: UnreachableRedis())
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["dependencies"]["redis"] == "unhealthy"

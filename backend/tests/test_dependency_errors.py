"""Optional graph failures remain actionable and do not disclose driver details."""

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.main import app
from app.config import Settings


@pytest.mark.parametrize("failure", [ServiceUnavailable, SessionExpired, AuthError])
def test_graph_failure_is_retryable_without_disclosing_connection(monkeypatch, failure):
    def unavailable(**_kwargs):
        raise failure("bolt://private-host:7687 password=private-secret")

    monkeypatch.setattr("app.graphsvc.queries.overview", unavailable)
    client = TestClient(app)
    response = client.get("/api/graph/overview")
    assert response.status_code == 503
    assert "Neo4j" in response.json()["detail"]
    assert "重试" in response.json()["detail"]
    assert "private-" not in response.text
    assert client.get("/api/papers").status_code == 200


@pytest.mark.parametrize("profile", [{"offline_mode": True}, {"access_mode": "multiuser"}])
def test_offline_profiles_disable_all_model_clients_even_with_a_key(profile):
    settings = Settings(_env_file=None, dashscope_api_key="synthetic-key",
                        research_model_enabled=True, **profile)
    assert settings.dashscope_api_key == ""
    assert not settings.research_model_enabled

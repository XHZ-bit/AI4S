"""Mock transport and synthetic facts only; not real-model quality evidence."""

import json
import logging

import httpx
import pytest
import respx

from app.config import get_settings
from app.models.research import PlanGenerateRequest
from app.research import service
from app.research.model_runtime import ResearchModelError, model_call_scope, structured_chat
from app.research.plan_provider import PlanSuggestions, selected_context, suggest_plan
from tests.test_research_t3_decision_planning import plan_input
from tests.test_research_extraction import _claim, _input, _passage

URL = "https://model.invalid/v1/chat/completions"


@pytest.fixture
def enabled(monkeypatch, isolated_services):
    monkeypatch.setattr(respx, "post", isolated_services.post)
    monkeypatch.setenv("RESEARCH_MODEL_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "https://model.invalid/v1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "synthetic-secret-never-log")
    get_settings.cache_clear()


def suggestion():
    return {"additional_steps": [{
        "title": "复核设置", "purpose": "验证当前证据",
        "procedure": ["人工核对原文，遇到缺失时暂停"],
        "acceptance_criteria": ["条件明确后才继续"], "evidence_ids": ["ev-1"],
    }]}


def response(content=None, **kwargs):
    return httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(suggestion() if content is None else content),
        }}], **kwargs,
    })


def call():
    return structured_chat([{"role": "user", "content": "private-source-text"}],
                           schema=PlanSuggestions.model_json_schema(),
                           prompt_version="test-prompt", schema_version="test-schema")


def test_disabled_never_calls_network():
    with pytest.raises(ResearchModelError, match="not_authorized"):
        call()


def test_model_transport_metadata_without_content(enabled, caplog):
    route = respx.post(URL).mock(return_value=response(usage={"total_tokens": 32}))
    caplog.set_level(logging.INFO, logger="app.research.model_runtime")
    with model_call_scope("task-synthetic"):
        assert json.loads(call())["additional_steps"]
    payload = json.loads(route.calls[0].request.content)
    assert payload["max_tokens"] == 2048
    assert payload["response_format"] == {"type": "json_object"}
    assert '"total_tokens": 32' in caplog.text
    assert "task-synthetic" in caplog.text
    assert "private-source-text" not in caplog.text
    assert "synthetic-secret-never-log" not in caplog.text


def test_strict_schema_and_single_task_budget(enabled, monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL_RESPONSE_FORMAT", "json_schema")
    monkeypatch.setenv("RESEARCH_MODEL_MAX_REQUESTS", "1")
    get_settings.cache_clear()
    route = respx.post(URL).mock(return_value=response())
    with model_call_scope("one"):
        call()
        with pytest.raises(ResearchModelError, match="request_budget"):
            call()
    assert route.call_count == 1
    schema = json.loads(route.calls[0].request.content)["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    step = schema["$defs"]["SuggestedStep"]
    assert set(step["required"]) == set(step["properties"])
    with model_call_scope("two"):
        call()
    assert route.call_count == 2


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_http_failure_no_retry_or_body_leak(enabled, status, caplog):
    route = respx.post(URL).mock(return_value=httpx.Response(status, text="secret source"))
    with pytest.raises(ResearchModelError, match="model_http_error") as error:
        call()
    assert route.call_count == 1
    assert error.value.retryable == (status in {429, 500})
    assert "secret source" not in caplog.text


def test_timeout_and_truncation_fail(enabled):
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("secret source"))
    with pytest.raises(ResearchModelError, match="model_timeout"):
        call()
    route.mock(side_effect=None, return_value=httpx.Response(200, json={"choices": [{
        "finish_reason": "length", "message": {"content": "{}"},
    }]}))
    with pytest.raises(ResearchModelError, match="incomplete"):
        call()


def test_provider_sends_only_selected_facts(enabled):
    value = plan_input()
    route = respx.post(URL).mock(return_value=response())
    output = suggest_plan(value)
    assert output["additional_steps"][0]["evidence_ids"] == ["ev-1"]
    sent = json.loads(json.loads(route.calls[0].request.content)["messages"][1]["content"])
    assert {m["id"] for m in sent["context"]["methods"]} == {value.decision.selected_method_id}
    assert {s["id"] for s in selected_context(value)["experiment_settings"]} == set(value.decision.selected_experiment_setting_ids)


@pytest.mark.parametrize("payload", [
    {"additional_steps": []}, {"additional_steps": [], "invented": True},
    {"additional_steps": [{**suggestion()["additional_steps"][0], "evidence_ids": ["foreign"]}]},
    {"additional_steps": [{**suggestion()["additional_steps"][0], "procedure": ["pip install unknown"]}]},
])
def test_provider_rejects_empty_unsafe_and_foreign_evidence(enabled, payload):
    respx.post(URL).mock(return_value=response(payload))
    with pytest.raises(ResearchModelError):
        suggest_plan(plan_input())


def test_service_never_swallows_failed_provider(monkeypatch):
    value = plan_input()
    monkeypatch.setattr(service.store, "get_project", lambda *args: value.project)
    monkeypatch.setattr(service.store, "get_decision", lambda *args: value.decision)
    monkeypatch.setattr(service, "project_facts", lambda *args: value)

    def fail(_value):
        raise RuntimeError("private provider response")

    monkeypatch.setattr(service, "plan_suggestion_provider", fail)
    with pytest.raises(ResearchModelError, match="model_provider_failed"):
        service.build_plan(None, value.project.id, PlanGenerateRequest(
            expected_project_version=value.project.version,
            decision_id=value.decision.id, decision_version=value.decision.version,
        ))


def test_configured_provider_used_by_production_service(enabled, monkeypatch):
    value = plan_input()
    monkeypatch.setattr(service.store, "get_project", lambda *args: value.project)
    monkeypatch.setattr(service.store, "get_decision", lambda *args: value.decision)
    monkeypatch.setattr(service, "project_facts", lambda *args: value)
    monkeypatch.setattr(service, "plan_suggestion_provider", None)
    route = respx.post(URL).mock(return_value=response())
    draft = service.build_plan(None, value.project.id, PlanGenerateRequest(
        expected_project_version=value.project.version,
        decision_id=value.decision.id, decision_version=value.decision.version,
    ))
    assert route.call_count == 1
    assert draft.title.startswith("[模型建议·待人工确认]")
    assert draft.steps[-1].id == "model-suggestion-1"
    assert draft.status.value == "draft" and draft.id is None
    assert draft.source_kind.value == "model_suggestion"


def test_input_budget_blocks_before_network(enabled, monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL_MAX_INPUT_CHARS", "1000")
    get_settings.cache_clear()
    with pytest.raises(ResearchModelError, match="input_budget"):
        structured_chat([{"role": "user", "content": "x" * 1001}], schema={},
                        prompt_version="test", schema_version="test")


def test_extraction_validation_error_does_not_echo_model_body():
    from app.research_extraction.candidates import ModelOutputError, _parse_model_output
    with pytest.raises(ModelOutputError) as error:
        _parse_model_output('{"private_source":"not-for-logs"}')
    assert "not-for-logs" not in str(error.value)


def test_provider_failure_is_persisted_without_raw_error(tmp_path):
    from app.db.sqlite import connect
    from app.db import projects as store
    from app.models.research import ResearchProjectCreate, TaskKind
    connection = connect(str(tmp_path / "failure.sqlite3"))
    try:
        project = store.create_project(connection, ResearchProjectCreate(
            title="Synthetic task failure", research_question="Failure retention?",
            domain="image_anomaly_detection", constraints=plan_input().project.constraints,
        ))
        task, _ = store.get_or_create_task(connection, TaskKind.PLAN_GENERATION,
                                            project.id, {})
        failed = service._task_failure(connection, task.id,
                                       ResearchModelError("model_timeout", retryable=True))
        assert failed.status.value == "failed" and failed.result is None
        assert failed.error.code == "model_timeout" and failed.error.retryable
    finally:
        connection.close()


def test_sentence_spanning_name_is_not_silently_trimmed(monkeypatch):
    from app.research_extraction.candidates import extract_candidates
    text = "Internal evaluation notice. The Example Probe method uses local features."
    payload = {"methods": [{
        "local_id": "m", "claim_role": "current_paper_method",
        "name": _claim("Internal evaluation notice. The Example Probe", "p1", text),
    }]}
    monkeypatch.setattr("app.research_extraction.candidates.chat", lambda *a, **kw: json.dumps(payload))
    bundle = extract_candidates(_input([_passage("p1", text)]))
    assert not bundle.methods
    assert any("method_name_boundary_ambiguous" in warning for warning in bundle.warnings)


def test_production_extraction_adapter_and_metadata_separation(enabled):
    from app.research_extraction.candidates import extract_candidates
    text = "Example Probe uses local features."
    payload = {"methods": [{"local_id": "m", "claim_role": "current_paper_method",
                             "name": _claim("Example Probe", "p1", text)}]}
    route = respx.post(URL).mock(return_value=response(payload))
    with model_call_scope("extract-synthetic"):
        bundle = extract_candidates(_input([_passage("p1", text)]))
    assert bundle.methods[0].name == "Example Probe"
    assert bundle.methods[0].status.value == "candidate"
    request = json.loads(route.calls[0].request.content)
    message = json.loads(request["messages"][1]["content"])
    assert message["passage_text"] == text
    assert "text" not in message["locator_metadata"]
    assert bundle.extraction_version.startswith("research-extraction-prompt-v2:")


def test_extraction_task_budget_does_not_return_partial_success(enabled, monkeypatch):
    from app.research_extraction.candidates import extract_candidates
    monkeypatch.setenv("RESEARCH_MODEL_MAX_REQUESTS", "1")
    get_settings.cache_clear()
    route = respx.post(URL).mock(return_value=response({"methods": []}))
    with model_call_scope("extract-budget"):
        with pytest.raises(ResearchModelError, match="request_budget"):
            extract_candidates(_input([_passage("p1", "Source one."), _passage("p2", "Source two.")]))
    assert route.call_count == 1

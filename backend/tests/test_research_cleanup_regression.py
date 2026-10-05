"""Cleanup/refactoring regressions: synthetic input and mocked transport only."""

import copy

import httpx
import pytest

from app.config import get_settings
from app.research.model_runtime import ResearchModelError, strict_schema, structured_chat
from app.research.suggestion_validation import PlanSuggestions, validate_suggestion_steps


def suggestion():
    return {"additional_steps": [{
        "title": "核对条件", "purpose": "确认依据",
        "procedure": ["人工核对原文"], "acceptance_criteria": ["条件明确"],
        "evidence_ids": ["ev-1"],
    }]}


@pytest.mark.parametrize("choices", [None, {}, [], [None], ["invalid"], [{}], [{"message": None}]])
def test_malformed_choices_fail_with_safe_error(monkeypatch, isolated_services, choices):
    monkeypatch.setenv("RESEARCH_MODEL_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "https://model.invalid/v1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "synthetic-test-key")
    get_settings.cache_clear()
    route = isolated_services.post("https://model.invalid/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": choices}))
    with pytest.raises(ResearchModelError, match="model_invalid_response"):
        structured_chat([{"role": "user", "content": "synthetic input"}],
                        schema=PlanSuggestions.model_json_schema(),
                        prompt_version="test", schema_version="test")
    assert route.call_count == 1


def test_strict_schema_preserves_property_names_and_literal_data():
    original = {"type": "object", "properties": {
        "default": {"type": "string", "default": "removed annotation"},
        "value": {"const": {"default": "literal retained"}},
    }}
    before = copy.deepcopy(original)
    converted = strict_schema(original)
    assert original == before
    assert converted["properties"]["default"] == {"type": "string"}
    assert converted["properties"]["value"]["const"] == {"default": "literal retained"}
    assert set(converted["required"]) == {"default", "value"}
    assert converted["additionalProperties"] is False


@pytest.mark.parametrize("evidence_ids", [None, "ev-1", {}, [{}], [], ["foreign"]])
def test_invalid_evidence_shape_is_rejected_without_crashing(evidence_ids):
    payload = suggestion()
    payload["additional_steps"][0]["evidence_ids"] = evidence_ids
    steps, errors = validate_suggestion_steps(payload, {"ev-1"})
    assert not steps
    assert "缺少当前课题证据" in errors[0]


@pytest.mark.parametrize("command", ["`python3 run.py`", "pip install unknown", "运行 bash script.sh"])
def test_commands_in_inputs_are_rejected(command):
    payload = suggestion()
    payload["additional_steps"][0]["inputs"] = [command]
    steps, errors = validate_suggestion_steps(payload, {"ev-1"})
    assert not steps
    assert "未经确认的命令" in errors[0]


def test_unknown_top_level_fields_reject_entire_suggestion():
    payload = suggestion()
    payload["model_override"] = "untrusted"
    steps, errors = validate_suggestion_steps(payload, {"ev-1"})
    assert not steps and errors


def test_valid_suggestion_and_blank_title():
    payload = suggestion()
    steps, errors = validate_suggestion_steps(payload, {"ev-1"})
    assert len(steps) == 1 and not errors
    assert steps[0].id == "model-suggestion-1"
    payload["additional_steps"][0]["title"] = "  "
    steps, errors = validate_suggestion_steps(payload, {"ev-1"})
    assert not steps and errors

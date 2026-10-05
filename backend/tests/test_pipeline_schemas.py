import pytest

from app.pipeline.prompts import build_messages
from app.pipeline.schemas import ExtractionResult, parse_extraction

VALID = """
{
  "entities": [
    {"type": "method", "name": "PPO", "confidence": 0.95, "evidence": "we use PPO"},
    {"type": "concept", "name": "clip objective", "confidence": 0.8, "evidence": "clip"}
  ],
  "relations": [
    {"rel_type": "USES", "src_name": "Diffusion Policy", "dst_name": "PPO",
     "confidence": 0.9, "evidence": "trained with PPO"}
  ]
}
"""


def test_parse_extraction_valid():
    res = parse_extraction(VALID)
    assert isinstance(res, ExtractionResult)
    assert res.entities[0].name == "PPO"
    assert res.relations[0].rel_type == "USES"


def test_parse_extraction_strips_code_fence():
    res = parse_extraction(f"```json\n{VALID}\n```")
    assert len(res.entities) == 2


def test_parse_extraction_rejects_bad_type():
    with pytest.raises(ValueError):
        parse_extraction('{"entities": [{"type": "alien", "name": "x", "confidence": 1.0, "evidence": "e"}], "relations": []}')


def test_parse_extraction_rejects_bad_rel_type():
    with pytest.raises(ValueError):
        parse_extraction('{"entities": [], "relations": [{"rel_type": "MARRIES", "src_name": "a", "dst_name": "b", "confidence": 0.9, "evidence": "e"}]}')


def test_parse_extraction_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_extraction("not json at all")


def test_build_messages_contains_schema_and_text():
    msgs = build_messages("T", "Abstract text", "Intro excerpt")
    assert msgs[0]["role"] == "system"
    assert "PREREQUISITE_OF" in msgs[0]["content"]
    user = msgs[-1]
    assert "T" in user["content"] and "Abstract text" in user["content"] and "Intro excerpt" in user["content"]

def test_parse_extraction_normalizes_common_relation_alias():
    raw = '{"entities": [], "relations": [{"rel_type": "USE", "src_name": "a", "dst_name": "b", "confidence": 0.9}]}'
    assert parse_extraction(raw).relations[0].rel_type == "USES"


def test_parse_extraction_keeps_valid_items_when_one_item_is_invalid():
    raw = '{"entities": [{"type": "method", "name": "PPO", "confidence": 0.9}, {"type": "alien", "name": "x", "confidence": 1}], "relations": []}'
    result = parse_extraction(raw)
    assert [entity.name for entity in result.entities] == ["PPO"]

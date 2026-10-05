"""抽取结果 Schema：类型与关系词表校验（设计文档 §3）。"""
import json
import re

from pydantic import BaseModel, Field, field_validator

ENTITY_TYPES = {"paper", "concept", "method", "dataset", "benchmark", "resource", "author"}
RELATION_ALIASES = {
    "USE": "USES", "EVALUATE_ON": "EVALUATES_ON", "IMPROVE_ON": "IMPROVES_ON",
    "COMPARE_WITH": "COMPARED_WITH", "PREREQUISITE": "PREREQUISITE_OF",
    "HAS_RESOURCES": "HAS_RESOURCE", "SUBTOPIC": "SUBTOPIC_OF",
}

RELATION_TYPES = {
    "CITES", "PROPOSES", "USES", "EVALUATES_ON", "IMPROVES_ON",
    "COMPARED_WITH", "PREREQUISITE_OF", "HAS_RESOURCE", "SUBTOPIC_OF",
}


class ProposedEntity(BaseModel):
    type: str
    name: str
    confidence: float = Field(ge=0, le=1)
    evidence: str = ""

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type: {v}")
        return v


class ProposedRelation(BaseModel):
    rel_type: str
    src_name: str
    dst_name: str
    confidence: float = Field(ge=0, le=1)
    evidence: str = ""

    @field_validator("rel_type")
    @classmethod
    def _check_rel(cls, v: str) -> str:
        v = v.upper().strip()
        v = RELATION_ALIASES.get(v, v)
        if v not in RELATION_TYPES:
            raise ValueError(f"unknown relation type: {v}")
        return v


class ExtractionResult(BaseModel):
    entities: list[ProposedEntity] = []
    relations: list[ProposedRelation] = []


def parse_extraction(raw: str) -> ExtractionResult:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid extraction json: {exc}") from exc

    entities: list[ProposedEntity] = []
    relations: list[ProposedRelation] = []
    errors: list[str] = []
    for item in data.get("entities", []):
        try:
            entities.append(ProposedEntity.model_validate(item))
        except Exception as exc:
            errors.append(f"entity: {exc}")
    for item in data.get("relations", []):
        try:
            relations.append(ProposedRelation.model_validate(item))
        except Exception as exc:
            errors.append(f"relation: {exc}")
    if errors and not entities and not relations:
        raise ValueError("; ".join(errors))
    return ExtractionResult(entities=entities, relations=relations)
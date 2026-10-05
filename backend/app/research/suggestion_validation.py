"""Shared pure validation for model suggestions; no transport or persistence."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.research import ProtocolStep

_COMMAND_PATTERN = re.compile(
    r"(?<![\w-])(?:pip\d*|conda|python\d*(?:\.\d+)?|docker|git|bash|powershell|cuda_visible_devices)\s+",
    re.IGNORECASE,
)
_UNVERIFIED_RESULT_PATTERN = re.compile(
    r"\b(?:auroc|auc|rmse|mae|mape|accuracy|精度|准确率)\b[^\n]{0,24}\d",
    re.IGNORECASE,
)


class SuggestedStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1000)
    inputs: list[str] = Field(default_factory=list, max_length=20)
    procedure: list[str] = Field(min_length=1, max_length=20)
    expected_observation: str | None = None
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)


class PlanSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    additional_steps: list[SuggestedStep] = Field(min_length=1, max_length=8)


def validate_suggestion_steps(
    suggestions: Any, known_evidence_ids: set[str],
) -> tuple[list[ProtocolStep], list[str]]:
    """Return accepted steps and safe diagnostics without echoing model output.

    The pure template caller may use an empty list. Production additionally
    requires PlanSuggestions, which disallows an empty generation response.
    """
    if not isinstance(suggestions, dict):
        return [], ["模型输出不是对象，已拒绝"]
    if set(suggestions) - {"additional_steps"}:
        return [], ["模型输出包含未允许字段，已拒绝写入方案"]
    raw_steps = suggestions.get("additional_steps", [])
    if not isinstance(raw_steps, list) or len(raw_steps) > 8:
        return [], ["模型 additional_steps 不是允许范围内的列表，已拒绝"]
    accepted: list[ProtocolStep] = []
    rejected: list[str] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            rejected.append(f"模型步骤 {index} 不是对象，已拒绝")
            continue
        evidence_ids = raw.get("evidence_ids")
        if (not isinstance(evidence_ids, list) or not evidence_ids
                or not all(isinstance(item, str) for item in evidence_ids)
                or not set(evidence_ids).issubset(known_evidence_ids)):
            rejected.append(f"模型步骤 {index} 缺少当前课题证据，已拒绝")
            continue
        try:
            step = SuggestedStep.model_validate(raw)
        except ValidationError:
            rejected.append(f"模型步骤 {index} 结构无效，已拒绝")
            continue
        text = "\n".join([step.title, step.purpose, *step.inputs, *step.procedure,
                          *step.acceptance_criteria, step.expected_observation or ""])
        if _COMMAND_PATTERN.search(text):
            rejected.append(f"模型步骤 {index} 含未经确认的命令，已拒绝")
            continue
        if _UNVERIFIED_RESULT_PATTERN.search(text):
            rejected.append(f"模型步骤 {index} 含未经核验的实测成绩，已拒绝")
            continue
        accepted.append(ProtocolStep(id=f"model-suggestion-{index + 1}", **step.model_dump()))
    return accepted, rejected

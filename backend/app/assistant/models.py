"""Additive assistant-v1 contracts; research-v1.1 remains unchanged."""
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field
from app.models.research import ProjectConstraints


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(Model):
    kind: Literal["fact", "evidence", "passage", "source", "document", "snapshot"]
    id: str
    paper_uid: str | None = None
    document_id: str | None = None
    document_version: str | None = None
    page: int | None = None
    line: int | None = None
    quote: str | None = None


class Target(Model):
    scope: Literal["project", "paper", "case"]
    id: str
    view: str = "overview"
    focus: str | None = None


class Action(Model):
    id: str
    title: str
    reason: str
    impact: str
    priority: int = Field(ge=0, le=4)
    target: Target
    references: list[Reference] = Field(default_factory=list)


class Check(Model):
    dimension: str
    status: Literal["match", "conflict", "unknown", "not_applicable"]
    actual: str | float | None = None
    limit: str | float | None = None
    reason: str
    references: list[Reference] = Field(default_factory=list)
    utilization: float | None = None


class CandidateChecks(Model):
    id: str
    method_id: str
    label: str
    method_status: str | None = None
    setting_status: str | None = None
    status: Literal["match", "conflict", "unknown", "not_applicable"]
    checks: list[Check]


class Exercise(Model):
    id: str
    kind: Literal["shape", "choice"]
    prompt: str
    parameters: dict[str, int] = Field(default_factory=dict)
    options: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    result: dict | None = None


class Report(Model):
    contract_version: Literal["assistant-v1"] = "assistant-v1"
    rule_version: str = "atlas-actions-1"
    input_fingerprint: str
    actions: list[Action] = Field(default_factory=list)
    candidates: list[CandidateChecks] = Field(default_factory=list)
    exercises: list[Exercise] = Field(default_factory=list)
    coverage: dict[str, int] = Field(default_factory=dict)
    notice: str = "自动分析用于发现缺口与指导下一步，资料原有状态保持可见。"


class Scenario(Model):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=100)
    constraints: ProjectConstraints


class ScenarioRequest(Model):
    expected_project_version: int = Field(ge=1)
    input_fingerprint: str
    scenarios: list[Scenario] = Field(min_length=1, max_length=4)


class ScenarioResult(Model):
    contract_version: Literal["assistant-v1"] = "assistant-v1"
    input_fingerprint: str
    baseline: list[CandidateChecks]
    scenarios: list[dict]


class PracticeAnswer(Model):
    version: int = Field(ge=0)
    shape: list[Annotated[int, Field(strict=True, ge=1, le=4096)]] | None = Field(default=None, min_length=3, max_length=3)
    choice: int | None = Field(default=None, ge=0, le=2, strict=True)


class ExplainRequest(Model):
    scope: Literal["project", "paper", "case"]
    id: str = Field(min_length=1)
    session_id: str | None = None
    input_fingerprint: str
    action_ids: list[str] = Field(min_length=1, max_length=8)


class Resource(Model):
    id: str
    kind: Literal["pdf", "source", "diagram", "animation"]
    title: str
    origin: Literal["literature", "source_repo", "illustrative"]
    version: str
    paper_uid: str | None = None
    document_id: str | None = None
    text: str | None = None
    url: str | None = None
    line: int | None = None
    tasks: list[str] = Field(default_factory=list)
    passages: list[dict] = Field(default_factory=list)


class ResourceList(Model):
    contract_version: Literal["assistant-v1"] = "assistant-v1"
    input_fingerprint: str
    items: list[Resource]

from pydantic import BaseModel, Field


class LearnerProfile(BaseModel):
    target_uid: str | None = None
    known_concepts: list[str] = []
    weekly_hours: float = Field(default=10.0, ge=1, le=80)
    goal: str


class GenerateRequest(BaseModel):
    profile: LearnerProfile


class RoadmapItem(BaseModel):
    task_id: str | None = None
    evidence_ids: list[str] = []
    kind: str
    uid: str | None = None
    title: str
    reason: str
    evidence: str
    difficulty: float | None = None
    done: bool = False


class RoadmapPhase(BaseModel):
    phase: int
    title: str
    weeks: str
    items: list[RoadmapItem]


class InnovationSuggestion(BaseModel):
    title: str
    rationale: str
    evidence: str


class RoadmapResult(BaseModel):
    version: int = 1
    stale: bool = False
    knowledge_ids: list[int] = []
    id: int | None = None
    goal: str
    phases: list[RoadmapPhase]
    innovations: list[InnovationSuggestion] = []
    created_at: str | None = None

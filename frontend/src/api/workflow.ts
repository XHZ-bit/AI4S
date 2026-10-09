import { apiGet, apiPost } from "./client";

export type ActivityStatus = "pending" | "in_progress" | "completed" | "needs_review";
export type EvidenceLevel = "none" | "recorded" | "checked";
export type ActivityKind = "roadmap" | "paper" | "case" | "project";

export interface WorkflowActivity {
  id: string;
  source_kind: ActivityKind;
  source_id: string;
  source_version: string | number;
  project_id: string | null;
  item_id: string;
  title: string;
  status: ActivityStatus;
  evidence_level: EvidenceLevel;
  url: string;
  detail: string;
  estimated_minutes: number | null;
  evidence_ids: string[];
}

export interface WorkflowOverview {
  counts: Record<ActivityStatus, number>;
  next: WorkflowActivity[];
  snapshot_required: number;
  total: number;
}

export interface Mastery {
  concept_uid: string;
  confirmed: number;
  version: number;
  reason: string;
  activity_id: string | null;
  updated_at: string | null;
}

export interface StepRecord {
  snapshot_id: string;
  step_id: string;
  version: number;
  done: number;
  outcome: string;
  updated_at: string | null;
}

export const workflowOverview = () => apiGet<WorkflowOverview>("/api/workflow/v1/overview");
export const workflowActivities = (params?: Record<string, unknown>) => apiGet<{items: WorkflowActivity[]; total: number; offset: number; limit: number}>("/api/workflow/v1/activities", params);
export const listMastery = () => apiGet<{items: Mastery[]}>("/api/workflow/v1/mastery");
export const getMastery = (uid: string) => apiGet<Mastery>(`/api/workflow/v1/mastery/${encodeURIComponent(uid)}`);
export const changeMastery = (uid: string, body: {expected_version: number; action: "confirm" | "revoke"; reason: string; activity_id?: string | null}) => apiPost<Mastery>(`/api/workflow/v1/mastery/${encodeURIComponent(uid)}`, body);
export const getStepRecord = (projectId: string, snapshotId: string, stepId: string) => apiGet<StepRecord>(`/api/workflow/v1/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}/steps/${encodeURIComponent(stepId)}`);
export const saveStepRecord = (projectId: string, snapshotId: string, stepId: string, body: {expected_version: number; done: boolean; outcome: string}) => apiPost<StepRecord>(`/api/workflow/v1/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}/steps/${encodeURIComponent(stepId)}`, body);

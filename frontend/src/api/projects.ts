import { authenticatedFetch } from "./session";
import type {
  AsyncTask,
  ComparisonRequest,
  ComparisonResult,
  DecisionListResponse,
  ExtractionStartRequest,
  GraphQueryResult,
  GraphProjectionStatus,
  PaperLink,
  PaperLinkCreate,
  PaperLinkListResponse,
  PaperLinkPatch,
  PlanGenerateRequest,
  PlanListResponse,
  PlanSaveRequest,
  ProjectFactsResponse,
  ProjectListResponse,
  ProjectSnapshot,
  ResearchDecision,
  ResearchDecisionCreate,
  ResearchProject,
  ResearchProjectCreate,
  ResearchProjectPatch,
  SnapshotCreateRequest,
  SnapshotListResponse,
  StatusTransitionRequest,
  ValidationPlan,
} from "./project-types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ProjectApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly retryable: boolean;
  readonly currentVersion: number | null;
  readonly fields: Record<string, string>;

  constructor(
    status: number,
    message: string,
    detail?: {
      code?: string;
      retryable?: boolean;
      current_version?: number | null;
      fields?: Record<string, string>;
    },
  ) {
    super(message);
    this.name = "ProjectApiError";
    this.status = status;
    this.code = detail?.code ?? null;
    this.retryable = detail?.retryable ?? false;
    this.currentVersion = detail?.current_version ?? null;
    this.fields = detail?.fields ?? {};
  }
}

async function parseError(response: Response): Promise<ProjectApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ProjectApiError(response.status, `${response.status} ${response.statusText}`);
  }
  const raw = body && typeof body === "object" && "detail" in body
    ? (body as { detail: unknown }).detail
    : body;
  if (typeof raw === "string") return new ProjectApiError(response.status, raw);
  if (Array.isArray(raw)) {
    const message = raw
      .map(item => item && typeof item === "object" && "msg" in item ? String(item.msg) : JSON.stringify(item))
      .join("；");
    return new ProjectApiError(response.status, message || "请求校验失败");
  }
  if (raw && typeof raw === "object") {
    const detail = raw as {
      code?: string;
      message?: string;
      retryable?: boolean;
      current_version?: number | null;
      fields?: Record<string, string>;
    };
    return new ProjectApiError(
      response.status,
      detail.message ?? `${response.status} ${response.statusText}`,
      detail,
    );
  }
  return new ProjectApiError(response.status, `${response.status} ${response.statusText}`);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  params?: Record<string, string | number | boolean | readonly string[] | null | undefined>,
): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach(item => url.searchParams.append(key, item));
    else if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, String(value));
  });
  const response = await authenticatedFetch(url, options);
  if (!response.ok) throw await parseError(response);
  if (options.method && options.method !== "GET") window.dispatchEvent(new Event("atlas:data-change"));
  return response.json() as Promise<T>;
}

const jsonOptions = (method: string, body?: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  headers: body === undefined ? undefined : { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
  signal,
});

export const isVersionConflict = (error: unknown): error is ProjectApiError =>
  error instanceof ProjectApiError && (error.status === 409 || error.code === "version_conflict");

export const listProjects = (
  params: { status?: string; domain?: string; cursor?: string; limit?: number } = {},
  signal?: AbortSignal,
) => request<ProjectListResponse>("/api/projects", { signal }, params);

export const getProject = (projectId: string, signal?: AbortSignal) =>
  request<ResearchProject>(`/api/projects/${encodeURIComponent(projectId)}`, { signal });

export interface ProjectAuditIssue {
  id: string;
  code: string;
  severity: "blocking" | "warning" | "notice";
  title: string;
  detail: string;
  fact_ids: string[];
  evidence_ids: string[];
  paper_uids: string[];
  affected_plan_ids: string[];
  affected_snapshot_ids: string[];
}

export interface ProjectAudit {
  contract_version: "project-audit-v1";
  rule_version: string;
  project_id: string;
  input_fingerprint: string;
  summary: Record<ProjectAuditIssue["severity"], number>;
  issues: ProjectAuditIssue[];
  notice: string;
}

export const getProjectAudit = (projectId: string, signal?: AbortSignal) =>
  request<ProjectAudit>(`/api/projects/${encodeURIComponent(projectId)}/audit`, { signal });

export interface ProjectImpact {
  contract_version: "project-impact-v1";
  project_id: string;
  input_fingerprint: string;
  issues: { issue_id: string; code: string; severity: ProjectAuditIssue["severity"];
    source_refs: { kind: string; id: string }[];
    affected: { kind: "plan" | "snapshot" | "activity"; id: string; url: string; reason: string }[] }[];
  notice: string;
}
export const getProjectImpact = (projectId: string, signal?: AbortSignal) =>
  request<ProjectImpact>(`/api/projects/${encodeURIComponent(projectId)}/impact`, { signal });

export interface ImpactCheckpoint {
  checkpoint_id: string;
  project_id: string;
  input_fingerprint: string;
  created_at: string;
}

export interface ImpactChanges {
  contract_version: "project-impact-changes-v1";
  project_id: string;
  checkpoint_id: string;
  baseline_created_at: string;
  baseline_fingerprint: string;
  current_fingerprint: string;
  added: ProjectAuditIssue[];
  resolved: ProjectAuditIssue[];
  changed: { before: ProjectAuditIssue; after: ProjectAuditIssue }[];
  notice: string;
}

export const getImpactCheckpoint = (projectId: string, signal?: AbortSignal) =>
  request<{ checkpoint: ImpactCheckpoint | null }>(
    `/api/projects/${encodeURIComponent(projectId)}/impact/checkpoints`, { signal });

export const saveImpactCheckpoint = (projectId: string, expectedFingerprint: string) =>
  request<ImpactCheckpoint>(`/api/projects/${encodeURIComponent(projectId)}/impact/checkpoints`,
    jsonOptions("POST", { expected_fingerprint: expectedFingerprint }));

export const getImpactChanges = (projectId: string, checkpointId: string, signal?: AbortSignal) =>
  request<ImpactChanges>(`/api/projects/${encodeURIComponent(projectId)}/impact/changes`,
    { signal }, { checkpoint_id: checkpointId });

export interface ComparisonReadiness {
  contract_version: "comparison-readiness-v1";
  project_id: string;
  input_fingerprint: string;
  candidates: { setting_id: string; method_id: string; label: string; constraint_status: string;
    missing_fields: string[]; source_gaps?: string[]; evidence_gaps?: string[];
    constraint_gaps: { dimension: string; status: string; reason: string }[] }[];
  pairs: { left_setting_id: string; right_setting_id: string;
    status: "comparable" | "conflict" | "information_insufficient";
    missing_fields: string[]; conflicting_fields: string[]; next_action: string;
    condition_checks?: {field: string; status: "match" | "missing" | "conflict";
      left_value: string | null; right_value: string | null; reason: string}[];
    metric_checks?: {field: string; status: "missing" | "conflict";
      left_value: string | null; right_value: string | null; reason: string}[];
    shared_metrics?: {metric_name: string; metric_scope: string; scale: string;
      unit: string | null; aggregation: string | null;
      left_measurement_id: string; right_measurement_id: string}[];
    source_gaps?: string[]; evidence_gaps?: string[] }[];
  total_pairs: number;
  truncated: boolean;
  notice: string;
}
export const getComparisonReadiness = (projectId: string, signal?: AbortSignal) =>
  request<ComparisonReadiness>(`/api/projects/${encodeURIComponent(projectId)}/comparison-readiness`, { signal });

export interface LocalRadar {
  contract_version: "local-radar-v1";
  project_id: string;
  input_fingerprint: string;
  total: number;
  notice: string;
  items: {
    uid: string; title: string; year: number | null; source: string;
    source_url: string; match_reasons: string[]; potentially_affected_plan_ids: string[];
  }[];
}

export const getProjectRadar = (projectId: string, signal?: AbortSignal) =>
  request<LocalRadar>(`/api/projects/${encodeURIComponent(projectId)}/radar`, { signal });

export const createProject = (body: ResearchProjectCreate) =>
  request<ResearchProject>("/api/projects", jsonOptions("POST", body));

export const updateProject = (projectId: string, body: ResearchProjectPatch) =>
  request<ResearchProject>(`/api/projects/${encodeURIComponent(projectId)}`, jsonOptions("PATCH", body));

export const listProjectPapers = (projectId: string, signal?: AbortSignal) =>
  request<PaperLinkListResponse>(`/api/projects/${encodeURIComponent(projectId)}/papers`, { signal });

export const linkProjectPaper = (projectId: string, body: PaperLinkCreate) =>
  request<PaperLink>(`/api/projects/${encodeURIComponent(projectId)}/papers`, jsonOptions("POST", body));

export const updateProjectPaper = (projectId: string, linkId: string, body: PaperLinkPatch) =>
  request<PaperLink>(
    `/api/projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(linkId)}`,
    jsonOptions("PATCH", body),
  );

export const startProjectExtraction = (projectId: string, linkId: string, body: ExtractionStartRequest) =>
  request<AsyncTask>(
    `/api/projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(linkId)}/extractions`,
    jsonOptions("POST", body),
  );

export const getProjectTask = (taskId: string, signal?: AbortSignal) =>
  request<AsyncTask>(`/api/projects/tasks/${encodeURIComponent(taskId)}`, { signal });

export const retryProjectTask = (taskId: string) =>
  request<AsyncTask>(`/api/projects/tasks/${encodeURIComponent(taskId)}/retry`, jsonOptions("POST"));

export const getProjectFacts = (
  projectId: string,
  params: { kind?: string; status?: string; paper_link_id?: string } = {},
  signal?: AbortSignal,
) => request<ProjectFactsResponse>(`/api/projects/${encodeURIComponent(projectId)}/facts`, { signal }, params);

export const transitionFact = (
  projectId: string,
  factId: string,
  body: StatusTransitionRequest,
) => request<ProjectFactsResponse["methods"][number] | ProjectFactsResponse["experiment_settings"][number] | ProjectFactsResponse["measurements"][number]>(
  `/api/projects/${encodeURIComponent(projectId)}/facts/${encodeURIComponent(factId)}/status`,
  jsonOptions("PATCH", body),
);

export const reviseProjectFact = (projectId: string, factId: string, body: {
  expected_version: number; changes: Record<string, unknown>; evidence_ids: string[]; actor: string; reason: string;
}) => request<ProjectFactsResponse["methods"][number] | ProjectFactsResponse["experiment_settings"][number] | ProjectFactsResponse["measurements"][number]>(
  `/api/projects/${encodeURIComponent(projectId)}/facts/${encodeURIComponent(factId)}`, jsonOptions("PATCH", body));

export const compareProjectCandidates = (projectId: string, body: ComparisonRequest) =>
  request<ComparisonResult>(`/api/projects/${encodeURIComponent(projectId)}/comparisons`, jsonOptions("POST", body));

export const listProjectDecisions = (projectId: string, signal?: AbortSignal) =>
  request<DecisionListResponse>(`/api/projects/${encodeURIComponent(projectId)}/decisions`, { signal });

export const saveProjectDecision = (projectId: string, body: ResearchDecisionCreate) =>
  request<ResearchDecision>(`/api/projects/${encodeURIComponent(projectId)}/decisions`, jsonOptions("POST", body));

export const generateProjectPlan = (projectId: string, body: PlanGenerateRequest) =>
  request<AsyncTask>(`/api/projects/${encodeURIComponent(projectId)}/plans/generate`, jsonOptions("POST", body));

export const listProjectPlans = (projectId: string, signal?: AbortSignal) =>
  request<PlanListResponse>(`/api/projects/${encodeURIComponent(projectId)}/plans`, { signal });

export const saveProjectPlan = (projectId: string, planId: string, body: PlanSaveRequest) =>
  request<ValidationPlan>(
    `/api/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}`,
    jsonOptions("PUT", body),
  );

export const createProjectSnapshot = (projectId: string, body: SnapshotCreateRequest) =>
  request<ProjectSnapshot>(`/api/projects/${encodeURIComponent(projectId)}/snapshots`, jsonOptions("POST", body));

export const listProjectSnapshots = (projectId: string, signal?: AbortSignal) =>
  request<SnapshotListResponse>(`/api/projects/${encodeURIComponent(projectId)}/snapshots`, { signal });

export const getProjectSnapshot = (projectId: string, snapshotId: string, signal?: AbortSignal) =>
  request<ProjectSnapshot>(
    `/api/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}`,
    { signal },
  );

export const snapshotExportUrl = (projectId: string, snapshotId: string, format: "json" | "markdown") => {
  const path = `/api/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}/export`;
  const url = new URL(`${BASE}${path}`, window.location.origin);
  url.searchParams.set("format", format);
  return url.toString();
};

export const getProjectProjectionStatus = (projectId: string, snapshotId: string, signal?: AbortSignal) =>
  request<GraphProjectionStatus>(
    `/api/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}/projection`,
    { signal },
  );

export const retryProjectProjection = (projectId: string, snapshotId: string) =>
  request<AsyncTask>(
    `/api/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(snapshotId)}/projection/retry`,
    jsonOptions("POST"),
  );

export const getProjectGraph = (
  projectId: string,
  snapshotId: string,
  options: { node_ids?: string[]; kinds?: string[]; limit?: number } = {},
  signal?: AbortSignal,
) =>
  request<GraphQueryResult>(
    `/api/projects/${encodeURIComponent(projectId)}/graph`,
    { signal },
    { snapshot_id: snapshotId, ...options },
  );

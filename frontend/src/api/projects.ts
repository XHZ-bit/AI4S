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
  const response = await fetch(url, options);
  if (!response.ok) throw await parseError(response);
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

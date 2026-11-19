import { authenticatedFetch } from "./session";
import type { KnowledgeEvidence } from "./knowledge";

export type ImplementationKind = "source" | "teaching";
export type ImplementationStatus = "proposed" | "confirmed" | "rejected";
export interface ImplementationMapping {
  id: string;
  node_id: string;
  code_source_id?: string;
  code_block_id?: string;
  start_line?: number | null;
  end_line?: number | null;
  paper_span: string;
  code_span: string;
  explanation: string;
  status: ImplementationStatus;
  implementation_kind: ImplementationKind;
  revision: number;
  paper_evidence: KnowledgeEvidence | null;
  code_evidence: KnowledgeEvidence | null;
  stale: boolean;
  stale_reasons: string[];
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  practice_id?: string | null;
}
export interface ImplementationBlock {
  id: string;
  text: string;
  heading: string;
  metadata: Record<string, unknown>;
  ordinal: number;
}
export interface ImplementationCollection {
  generation?: "model" | "rule" | "cached";
  warning?: string;
  items: ImplementationMapping[];
  code_sources: {
    id: string;
    title: string;
    version: string;
    blocks: ImplementationBlock[];
  }[];
  paper_evidence: KnowledgeEvidence[];
}
export interface ImplementationInput {
  paper_evidence_id?: string;
  code_source_id: string;
  code_block_id: string;
  paper_span: string;
  code_span: string;
  explanation: string;
  implementation_kind: ImplementationKind;
  start_line?: number;
  end_line?: number;
}
const base = import.meta.env.VITE_API_BASE ?? "";
const root = (project: string, node: string) =>
  `${base}/api/projects/${encodeURIComponent(project)}/knowledge/nodes/${encodeURIComponent(node)}/implementations`;
async function request<T>(
  url: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await authenticatedFetch(url, {
    method,
    signal,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const detail = (await response.json()).detail;
      message =
        typeof detail === "string"
          ? detail
          : detail?.message || JSON.stringify(detail);
    } catch {
      /* preserve HTTP error */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const getImplementations = (
  project: string,
  node: string,
  signal?: AbortSignal,
) =>
  request<ImplementationCollection>(
    root(project, node),
    "GET",
    undefined,
    signal,
  );
export const generateImplementations = (
  project: string,
  node: string,
  body: { source_ids: string[]; refresh?: boolean },
) =>
  request<ImplementationCollection>(
    `${root(project, node)}/generate`,
    "POST",
    body,
  );
export const createImplementation = (
  project: string,
  node: string,
  body: ImplementationInput,
) => request<ImplementationMapping>(root(project, node), "POST", body);
export const patchImplementation = (
  project: string,
  node: string,
  id: string,
  body: Omit<
    Partial<ImplementationInput>,
    "paper_evidence_id" | "start_line" | "end_line"
  > & {
    expected_revision: number;
    paper_evidence_id?: string | null;
    start_line?: number | null;
    end_line?: number | null;
    status?: ImplementationStatus;
    practice_id?: string | null;
  },
) =>
  request<ImplementationMapping>(
    `${root(project, node)}/${encodeURIComponent(id)}`,
    "PATCH",
    body,
  );

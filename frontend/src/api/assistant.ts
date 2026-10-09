import { apiGet, apiPost } from "./client";
import type { ProjectConstraints } from "./project-types";
export type Scope = "project" | "paper" | "case";
export interface Reference { kind: string; id: string; paper_uid?: string | null; document_id?: string | null; document_version?: string | null; page?: number | null; line?: number | null; quote?: string | null }
export interface Action { id: string; title: string; reason: string; impact: string; priority: number; target: { scope: Scope; id: string; view: string; focus?: string | null }; references: Reference[] }
export interface Check { dimension: string; status: CheckStatus; actual: string | number | null; limit: string | number | null; reason: string; references: Reference[]; utilization?: number | null }
export type CheckStatus = "match" | "conflict" | "unknown" | "not_applicable";
export const statusLabels: Record<CheckStatus, string> = { match: "匹配", conflict: "冲突", unknown: "信息不足", not_applicable: "未设条件" };
export interface Candidate { method_status?: string | null; setting_status?: string | null; id: string; method_id: string; label: string; status: CheckStatus; checks: Check[] }
export interface Exercise { id: string; kind: "shape" | "choice"; prompt: string; parameters: Record<string, number>; options: string[]; references: Reference[]; result: { correct: boolean; explanation: string; attempts: number; answer: number | number[] } | null }
export interface Report { input_fingerprint: string; actions: Action[]; candidates: Candidate[]; coverage: Record<string, number>; exercises: Exercise[]; notice: string }
export interface Resource { id: string; kind: "pdf" | "source" | "diagram" | "animation"; title: string; origin: string; version: string; paper_uid?: string; document_id?: string; text?: string; url?: string; line?: number; tasks?: string[]; passages: { id: string; heading: string; text: string; page: number | null }[] }
export interface Scenario { id: string; label: string; constraints: ProjectConstraints }
export interface ScenarioResult { input_fingerprint: string; baseline: Candidate[]; scenarios: { id: string; label: string; candidates: Candidate[]; changes: { candidate_id: string; dimension: string; before: string; after: string; reason: string }[] }[] }
export interface Diff { changes: { path: string; before: unknown; after: unknown; kind: string }[]; affected: { snapshot_id: string; plan_id: string; fact_ids: string[]; step_ids: string[]; reason: string }[]; unresolved: string[] }
export const getInsights = (scope: Scope, id: string, sid?: string | null, signal?: AbortSignal) => {
  const url = scope === "project" ? `/api/projects/${encodeURIComponent(id)}/insights` : scope === "paper" ? `/api/learning/papers/${encodeURIComponent(id)}/coach` : `/api/cases/${encodeURIComponent(id)}/sessions/${encodeURIComponent(sid || "")}/coach`;
  return apiGet<Report>(url, undefined, signal);
};
export const getResources = (scope: Scope, id: string, signal?: AbortSignal) => apiGet<{ contract_version: "assistant-v1"; input_fingerprint: string; items: Resource[] }>("/api/resources", { scope, id }, signal);
export const evaluateScenarios = (id: string, version: number, fingerprint: string, scenarios: Scenario[], signal?: AbortSignal) => apiPost<ScenarioResult>(`/api/projects/${id}/scenarios/evaluate`, { expected_project_version: version, input_fingerprint: fingerprint, scenarios }, signal);
export const getDiff = (id: string, sid: string, against: string, signal?: AbortSignal) => apiGet<Diff>(`/api/projects/${id}/snapshots/${sid}/diff`, { against }, signal);
export const explainActions = (scope: Scope, id: string, report: Report, sid?: string | null) => apiPost<{ explanations: { action_id: string; text: string }[] }>("/api/assistant/explain", { scope, id, session_id: sid || null, input_fingerprint: report.input_fingerprint, action_ids: report.actions.slice(0, 3).map(a => a.id) });

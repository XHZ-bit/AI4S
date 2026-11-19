import {apiGet, apiPatch, apiPost} from './client';
import type {KnowledgeEdge, KnowledgeEvidence, KnowledgeGraph, KnowledgeNode} from './knowledge';

export type RouteStepState = 'todo' | 'done' | 'skipped';
export interface RouteSource {id: string; title: string; version: string; removed?: boolean}
export interface LearningRouteStep {
  node_id: string;
  label: string;
  role: 'target' | 'prerequisite';
  state: RouteStepState;
  snapshot: {node: KnowledgeNode; source: RouteSource | null; evidence: KnowledgeEvidence[]; prerequisites: KnowledgeEdge[]};
  available: boolean;
  stale: boolean;
  stale_reasons: string[];
  warnings?: string[];
  blocked_by?: string[];
  current_context: string | null;
  current_node: KnowledgeNode | null;
  current_evidence: KnowledgeEvidence[];
  current_source: RouteSource | null;
}
export interface LearningRoutePreview {
  target_node_id: string;
  target_label: string;
  research_question: string;
  preview_fingerprint: string;
  steps: LearningRouteStep[];
  edges: KnowledgeEdge[];
  warnings: string[];
  cycle_detected: boolean;
  truncated: boolean;
  graph: KnowledgeGraph;
}
export interface SavedLearningRoute extends LearningRoutePreview {
  id: string;
  revision: number;
  created_at: string;
  updated_at: string;
  reviewed_by: string | {id?: string; label?: string; name?: string};
  stale: boolean;
  question_changed: boolean;
  needs_replan?: boolean;
  next_node_id: string | null;
}
const root = (project: string) => `/api/projects/${encodeURIComponent(project)}/knowledge/learning-route`;
export const getLearningRoute = (project: string, signal?: AbortSignal) => apiGet<{route: SavedLearningRoute | null}>(root(project), undefined, signal);
export const previewLearningRoute = (project: string, target: string, signal?: AbortSignal) => apiPost<LearningRoutePreview>(root(project) + '/preview', {target_node_id: target}, signal);
export const saveLearningRoute = (project: string, preview: LearningRoutePreview, revision: number) => apiPost<{route: SavedLearningRoute}>(root(project), {expected_revision: revision, target_node_id: preview.target_node_id, preview_fingerprint: preview.preview_fingerprint});
export const updateLearningRoute = (project: string, body: {expected_revision: number; step_node_id?: string; state?: RouteStepState; order?: string[]}) => apiPatch<{route: SavedLearningRoute}>(root(project), body);
export const recheckLearningRoute = (project: string, revision: number, step: LearningRouteStep) => apiPost<{route: SavedLearningRoute}>(root(project) + '/recheck', {expected_revision: revision, step_node_id: step.node_id, expected_context: step.current_context});
export const getLearningRouteHistory = (project: string, signal?: AbortSignal) => apiGet<{items: SavedLearningRoute[]}>(root(project) + '/history', undefined, signal);

export function notifyLearningRoute(projectId: string) {
  window.dispatchEvent(new CustomEvent('paperstride:learning-route', {detail: {projectId}}));
}

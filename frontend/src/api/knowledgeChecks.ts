import {apiGet, apiPost} from './client';

export interface TeachingQuestion {
  id: string;
  version: number;
  title: string;
  question: string;
  choices: {id: string; text: string}[];
}
export interface CheckAttempt {
  id: string;
  node_id: string;
  question: string;
  answer: string;
  correct: boolean;
  feedback: string;
  explanation: string;
  stale: boolean;
  dismissed: boolean;
  created_at: string;
}
export interface CheckRecommendation {
  attempt_id: string;
  node_id: string;
  label: string;
  source_node_id: string;
  source_node_label: string;
  reason: string;
  answer: string;
  question: string;
}
export interface NodeChecks {
  questions: TeachingQuestion[];
  history: CheckAttempt[];
  context_fingerprint: string;
  available: boolean;
}
const root = (project: string) => `/api/projects/${encodeURIComponent(project)}/knowledge`;
const nodeRoot = (project: string, node: string) => `${root(project)}/nodes/${encodeURIComponent(node)}/checks`;
export const getNodeChecks = (project: string, node: string, signal?: AbortSignal) =>
  apiGet<NodeChecks>(nodeRoot(project, node), undefined, signal);
export const answerNodeCheck = (project: string, node: string, check: string, body: {answer_id: string; expected_context: string; explanation: string}) =>
  apiPost<CheckAttempt>(`${nodeRoot(project, node)}/${encodeURIComponent(check)}`, body);
export const dismissNodeCheck = (project: string, node: string, attempt: string) =>
  apiPost<{dismissed: boolean}>(`${nodeRoot(project, node)}/${encodeURIComponent(attempt)}/dismiss`, {});
export const getCheckRecommendation = (project: string, signal?: AbortSignal) =>
  apiGet<{recommendation: CheckRecommendation | null}>(`${root(project)}/checks/recommendation`, undefined, signal);

import {apiGet, apiPatch, apiPost} from './client';
import type {KnowledgeEvidence, KnowledgeNode} from './knowledge';

export type ConceptDecision = 'comparable' | 'conditions_differ' | 'uncertain' | 'rejected';
export interface ConceptSide {
  node: KnowledgeNode;
  source_id: string;
  source_title: string;
  source_version: string;
  conditions: Record<string, unknown>;
  evidence: KnowledgeEvidence[];
  evidence_fingerprint: string;
  available: boolean;
}
export interface ConceptCorrespondence {
  id: string;
  left: ConceptSide;
  right: ConceptSide;
  current_left: ConceptSide | null;
  current_right: ConceptSide | null;
  status: ConceptDecision;
  explanation: string;
  revision: number;
  reviewed_by: string;
  reviewed_at: string;
  stale: boolean;
  stale_reasons: string[];
}
export interface ConceptCollection {
  node: ConceptSide;
  items: ConceptCorrespondence[];
  candidates: {side: ConceptSide; reason: string}[];
  choices: ConceptSide[];
  sources: {id: string; title: string}[];
  generation: 'local_rules';
  truncated: boolean;
}
export interface ConceptInput {
  other_node_id: string;
  status: ConceptDecision;
  explanation: string;
  left_node_version?: number;
  right_node_version?: number;
  left_source_version?: string;
  right_source_version?: string;
  left_evidence_fingerprint?: string;
  right_evidence_fingerprint?: string;
}
const root = (project: string, node: string) =>
  `/api/projects/${encodeURIComponent(project)}/knowledge/nodes/${encodeURIComponent(node)}/concept-correspondences`;
export const getConceptCorrespondences = (project: string, node: string, q = '', source?: string, signal?: AbortSignal) =>
  apiGet<ConceptCollection>(root(project, node), {q, source_id: source}, signal);
export const createConceptCorrespondence = (project: string, node: string, body: ConceptInput) =>
  apiPost<ConceptCorrespondence>(root(project, node), body);
export const reviseConceptCorrespondence = (project: string, node: string, id: string, body: Omit<ConceptInput, 'other_node_id'> & {expected_revision: number}) =>
  apiPatch<ConceptCorrespondence>(root(project, node) + '/' + encodeURIComponent(id), body);

import {apiGet, apiPatch, apiPost} from './client';
import type {KnowledgeEvidence} from './knowledge';

export type CoverageCategory = 'problem' | 'method' | 'experiment' | 'finding' | 'limitation';
export type CoverageDecisionStatus = 'not_reported' | 'not_applicable' | 'reset';
export interface CoverageItem {
  category: CoverageCategory;
  label: string;
  state: 'covered' | 'missing' | 'not_extracted' | 'not_reported' | 'not_applicable';
  node_count: number;
  evidence_count: number;
  nodes: {id: string; label: string; version: number}[];
  evidence: KnowledgeEvidence[];
  decision?: {status: CoverageDecisionStatus; reason: string; reviewed_by: string; reviewed_at: string} | null;
  decision_stale: boolean;
}
export interface SourceCoverageData {
  source_id: string;
  source_title: string;
  source_version: string;
  revision: number;
  parsed: boolean;
  analysis_running?: boolean;
  semantic_node_count: number;
  model_available: boolean;
  scope: string;
  items: CoverageItem[];
  notice?: string;
  supplement?: {category: CoverageCategory; added_or_refreshed: number; warnings: string[]};
}
interface ExpectedCoverage {
  category: CoverageCategory;
  expected_source_version: string;
  expected_revision: number;
}
const root = (project: string, source: string) =>
  `/api/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/coverage`;
export const getSourceCoverage = (project: string, source: string, signal?: AbortSignal) =>
  apiGet<SourceCoverageData>(root(project, source), undefined, signal);
export const supplementSourceCoverage = (project: string, source: string, body: ExpectedCoverage) =>
  apiPost<SourceCoverageData>(root(project, source) + '/supplement', body);
export const reviewSourceCoverage = (project: string, source: string, body: ExpectedCoverage & {status: CoverageDecisionStatus; reason: string}) =>
  apiPatch<SourceCoverageData>(root(project, source), body);

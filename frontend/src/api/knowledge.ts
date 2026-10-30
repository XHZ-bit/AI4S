import { authenticatedFetch } from './session';

export type WorkspaceMode = 'explore' | 'research' | 'reproduce';
export type WorkspaceView = 'graph' | 'reading' | 'learning' | 'compare' | 'practice' | 'materials';
export type SourceKind = 'paper' | 'report' | 'results' | 'code';
export interface KnowledgePreferences { mode: WorkspaceMode; view: string | null }
export interface AnalysisRun {
  id: string; project_id: string; source_id: string; status: string;
  stages: Record<'save' | 'parse' | 'extract' | 'graph', string>;
  progress: number; errors: string[]; warnings: string[]; usage: Record<string, unknown>;
  created_at: string; updated_at: string;
}
export interface SourceBlock {
  id: string; ordinal: number; kind: string; heading: string; text: string; page: number | null;
  bbox?: number[] | null; metadata: Record<string, unknown>;
}
export interface KnowledgeSource {
  id: string; project_id: string; asset_id: string; version: string; title: string;
  filename: string; kind: SourceKind; media_type: string; paper_uid?: string | null;
  url?: string | null; removed: boolean; created_at: string; analysis?: AnalysisRun; blocks?: SourceBlock[];
  knowledge_nodes?: {id:string;label:string;kind:string;block_ids:string[]}[];
  quality?: Record<string,unknown>; parser?:string; demo?:boolean;
}
export interface KnowledgeNode {
  id: string; project_id: string; source_id: string; kind: string; label: string; summary: string;
  parent_id: string | null; origin: string; research_status: string; version: number;
  hidden: boolean; source_missing: boolean; evidence_ids: string[]; metadata: Record<string, unknown>;
}
export interface KnowledgeEdge {
  id: string; project_id: string; source_id: string; source: string; target: string;
  kind: string; label: string; explanation: string; origin: string; version: number;
  hidden: boolean; source_missing: boolean; evidence_ids: string[]; metadata?: Record<string, unknown>;
}
export interface FormulaSource {
  evidence_id:string;block_id:string;source_id:string;label:string;latex?:string;recognition:string;
  page?:number|null;image_url?:string;
}
export interface KnowledgeEvidence {
  formula?:FormulaSource;
  id: string; source_id: string; source_title: string; block_id: string; quote: string;
  locator: {page?: number | null; bbox?: number[] | null; heading?: string | null; ordinal?: number | null;
    start_line?: number | null; end_line?: number | null; sheet?: string | null; cell_range?: string | null;
    path?:string | null; commit?:string | null; url?:string | null};
  source_version: string; origin: string;
}
export interface LearningResource { title?: string; name?: string; url?: string; reason?: string; description?: string; kind?: string; type?: string; fetched?: boolean; status?: string; content?: string }
export type LearningSection = 'overview' | 'definition' | 'derivation' | 'prerequisites' | 'implementation' | 'limitations';
export interface LearningOptions {goal?:string;depth?:'standard'|'deep'}
export interface LearningCoverage {status:'complete'|'partial';checks:{key:string;label:string;status:'complete'|'missing'|'not_applicable';required:boolean;note:string}[];missing:string[];verification:string}
export interface NodeDetail {
  formula_sources?:FormulaSource[];
  node: KnowledgeNode; edges: KnowledgeEdge[]; neighbors: KnowledgeNode[]; evidence: KnowledgeEvidence[];
  prerequisites: KnowledgeNode[]; resources: LearningResource[]; demos: string[];
}
export interface KnowledgeGraph {
  nodes: KnowledgeNode[]; edges: KnowledgeEdge[]; total_nodes: number; total_edges: number; truncated: boolean;
}
export interface LearningArtifact {
  goal?:string;depth?:'standard'|'deep';rules_version?:string;coverage?:LearningCoverage;
  variants?:{id:string;goal:string;depth:'standard'|'deep';status:string}[];
  context_summary?:{evidence_count:number;prerequisite_count:number;linked_code_sources:{id:string;title:string;version:string}[];source_versions:{id:string;version:string}[]};
  formula_sources?:FormulaSource[];
  id: string; node_id: string; node_version: number; status: string; stale: boolean; cached: boolean;
  sections: { overview: string; definition: string; derivation: string; prerequisites: string; implementation: string; limitations: string };
  evidence: KnowledgeEvidence[]; resources: LearningResource[]; demos: string[]; usage: Record<string, unknown>; errors: string[];
  revision?: number; user_edited_sections?: LearningSection[]; hidden_sections?: LearningSection[]; origin?: string;
}
export interface KnowledgeComparison {
  id: string; source_ids: string[]; title: string; revision?:number; dimensions?:string[]; auto_filled?:boolean;
  focus_node_ids?: string[]; focus_nodes?: {id:string;source_id:string;label:string}[];
  rows: {dimension: string; values: {source_id: string; text: string; node_ids: string[]; evidence_ids: string[]; origin: string}[]; compatibility: string}[];
  evidence: KnowledgeEvidence[]; status: string; cached: boolean; stale: boolean; usage: Record<string, unknown>; errors: string[];
}
export interface SourcesResponse { items: KnowledgeSource[]; preferences: KnowledgePreferences; model: { configured: boolean; enabled: boolean } }

const BASE = import.meta.env.VITE_API_BASE ?? '';
const root = (project: string) => `/api/projects/${encodeURIComponent(project)}`;
async function request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const form = body instanceof FormData;
  const response = await authenticatedFetch(BASE + path, { method, signal,
    headers: body === undefined || form ? undefined : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const detail = (await response.json()).detail;
      if (typeof detail === 'string') message = detail;
      else if (detail && typeof detail === 'object') message = detail.message || JSON.stringify(detail);
    } catch { /* Preserve HTTP failure when a proxy returns HTML. */ }
    throw Object.assign(new Error(message), {status: response.status});
  }
  return response.json() as Promise<T>;
}
export const sourceFileUrl = (project: string, source: string) => `${BASE}${root(project)}/sources/${encodeURIComponent(source)}/file`;
export const sourceImageUrl = (project: string, source: string, block: string) => `${BASE}${root(project)}/sources/${encodeURIComponent(source)}/images/${encodeURIComponent(block)}`;
export const listKnowledgeSources = (project: string, signal?: AbortSignal) => request<SourcesResponse>(`${root(project)}/sources?include_removed=true`, 'GET', undefined, signal);
export function uploadKnowledgeSource(project: string, file: File, kind?: SourceKind, signal?: AbortSignal) {
  const body = new FormData(); body.append('file', file); if(kind) body.append('kind', kind);
  return request<{source: KnowledgeSource; analysis: AnalysisRun}>(`${root(project)}/sources`, 'POST', body, signal);
}
export const linkKnowledgeSource = (project: string, url: string, kind?: SourceKind) => request<{source: KnowledgeSource; analysis: AnalysisRun}>(`${root(project)}/sources/link`, 'POST', {url,kind});
export const attachKnowledgePaper = (project: string, paper_uid: string) => request<{source: KnowledgeSource; analysis: AnalysisRun}>(`${root(project)}/sources/attach`, 'POST', {paper_uid});
export const getKnowledgeSource = (project: string, source: string, signal?: AbortSignal) => request<KnowledgeSource>(`${root(project)}/sources/${encodeURIComponent(source)}`, 'GET', undefined, signal);
export const patchKnowledgeSource = (project: string, source: string, body: {removed?: boolean; title?: string}) => request<KnowledgeSource>(`${root(project)}/sources/${encodeURIComponent(source)}`, 'PATCH', body);
export const analyzeKnowledgeSource = (project: string, source_id: string, retry = false) => request<AnalysisRun>(`${root(project)}/analysis`, 'POST', {source_id,retry});
export const listKnowledgeAnalysis = (project: string, signal?: AbortSignal) => request<{items: AnalysisRun[]}>(`${root(project)}/analysis`, 'GET', undefined, signal);
export const cancelKnowledgeAnalysis = (project: string, id: string) => request<AnalysisRun>(`${root(project)}/analysis/${encodeURIComponent(id)}/cancel`, 'POST', {});
export const saveKnowledgePreferences = (project: string, body: Partial<KnowledgePreferences>) => request<KnowledgePreferences>(`${root(project)}/knowledge/preferences`, 'PATCH', body);
export const getKnowledgeGraph = (project: string, params: {source_id?: string; node_id?: string; q?: string; kind?: string; limit?: number; include_hidden?: boolean; overview?: boolean} = {}, signal?: AbortSignal) => {
  const query = new URLSearchParams(); Object.entries(params).forEach(([k,v]) => { if(v !== undefined && v !== '') query.set(k,String(v)); });
  return request<KnowledgeGraph>(`${root(project)}/knowledge/graph?${query}`, 'GET', undefined, signal);
};
export const getKnowledgeNode = (project: string, node: string, signal?: AbortSignal) => request<NodeDetail>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}`, 'GET', undefined, signal);
export const patchKnowledgeNode = (project: string, node: string, body: {expected_version: number; label?: string; summary?: string; latex?:string; hidden?: boolean; research_status?: string}) => request<KnowledgeNode>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}`, 'PATCH', body);
export const patchKnowledgeEdge = (project: string, edge: string, body: {expected_version: number; label?: string; explanation?: string; hidden?: boolean}) => request<KnowledgeEdge>(`${root(project)}/knowledge/edges/${encodeURIComponent(edge)}`, 'PATCH', body);
export const mergeKnowledgeNodes = (project: string, node_ids: string[], label?: string) => request<KnowledgeNode>(`${root(project)}/knowledge/nodes/merge`, 'POST', {node_ids,label});
export const splitKnowledgeNode = (project: string, node: string) => request<unknown>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}/split`, 'POST', {});
export const getNodeLearning = (project:string,node:string,signal?:AbortSignal,options?:LearningOptions) => {const query=new URLSearchParams();if(options?.goal!==undefined)query.set('goal',options.goal);if(options?.depth)query.set('depth',options.depth);return request<LearningArtifact>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}/learning${query.size?'?'+query:''}`,'GET',undefined,signal)};
export const generateNodeLearning = (project:string,node:string,refresh=false,signal?:AbortSignal,options?:LearningOptions) => request<LearningArtifact>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}/learning`,'POST',{refresh,...options},signal);
export const patchNodeLearning = (project:string,node:string,body:{expected_revision:number;sections?:Partial<Record<LearningSection,string>>;hidden_sections?:LearningSection[];goal?:string;depth?:'standard'|'deep'},signal?:AbortSignal) => request<LearningArtifact>(`${root(project)}/knowledge/nodes/${encodeURIComponent(node)}/learning`,'PATCH',body,signal);
export const listKnowledgeComparisons = (project: string, signal?: AbortSignal) => request<{items: KnowledgeComparison[]}>(`${root(project)}/knowledge/comparisons`, 'GET', undefined, signal);
export const compareKnowledgeSources = (project: string, source_ids: string[], refresh = false, signal?: AbortSignal, focus_node_ids:string[] = [], dimensions?:string[]) => request<KnowledgeComparison>(`${root(project)}/knowledge/comparisons`, 'POST', {source_ids,refresh,focus_node_ids,dimensions}, signal);

export const nodeKindLabels: Record<string,string> = {paper:'论文',report:'研究报告',results:'实验结果',code:'代码',problem:'研究问题',contribution:'贡献',method:'方法',module:'模块',experiment:'实验',finding:'结果',limitation:'局限',concept:'概念',formula:'公式',algorithm:'算法',resource:'资源',hypothesis:'研究设想'};
export const originLabels: Record<string,string> = {source:'原文明示',inference:'平台归纳',user:'用户补充'};
export const researchStatusLabels: Record<string,string> = {unspecified:'未说明',proposed:'设想',implemented:'已实现',reported_result:'报告中已完成',pending_validation:'待验证'};
export const analysisStatusLabels: Record<string,string> = {queued:'等待处理',running:'正在处理',succeeded:'已完成',partial:'部分完成',failed:'处理失败',interrupted:'已中断',cancelled:'已取消'};

export const previewKnowledgeComparison = (project:string, sourceIds:string[], focusIds:string[]=[], dimensions?:string[], signal?:AbortSignal) => {
 const params=new URLSearchParams();sourceIds.forEach(id=>params.append('source_ids',id));focusIds.forEach(id=>params.append('focus_node_ids',id));dimensions?.forEach(d=>params.append('dimensions',d));
 return request<KnowledgeComparison>(`${root(project)}/knowledge/comparisons/preview?${params}`,'GET',undefined,signal);
};
export const reviseKnowledgeComparison=(project:string,id:string,body:{source_ids:string[];focus_node_ids?:string[];dimensions?:string[];expected_revision:number;dimension:string;source_id:string;text:string})=>request<KnowledgeComparison>(`${root(project)}/knowledge/comparisons/${encodeURIComponent(id)}`,'PATCH',body);

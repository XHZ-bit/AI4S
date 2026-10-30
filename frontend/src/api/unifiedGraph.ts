import {apiGet} from './client';
import type {KnowledgeNode,KnowledgeEdge,KnowledgeEvidence} from './knowledge';
export interface KnowledgeScope {id:string;kind:'library'|'project';project_id:string|null;title:string}
export interface UnifiedNode extends KnowledgeNode {scope?:KnowledgeScope;source_title?:string;paper_uid?:string;href?:string;quality_status?:string}
export interface UnifiedGraph {nodes:UnifiedNode[];edges:KnowledgeEdge[];total_nodes:number;total_edges:number;truncated:boolean;scopes:KnowledgeScope[];offset:number;overview?:boolean}
export const getUnifiedGraph=(params:Record<string,unknown>={},signal?:AbortSignal)=>apiGet<UnifiedGraph>('/api/knowledge/graph',params,signal);
export const getUnifiedNode=(id:string,signal?:AbortSignal)=>apiGet<{node:UnifiedNode;edges:KnowledgeEdge[];neighbors:UnifiedNode[];evidence:KnowledgeEvidence[];scope:KnowledgeScope}>('/api/knowledge/nodes/'+encodeURIComponent(id),undefined,signal);
export const getUnifiedEdge=(id:string,signal?:AbortSignal)=>apiGet<{edge:KnowledgeEdge;evidence:KnowledgeEvidence[];scope:KnowledgeScope}>('/api/knowledge/edges/'+encodeURIComponent(id),undefined,signal);
export interface KnowledgePath {nodes:KnowledgeNode[];edges:KnowledgeEdge[];paths:{node_ids:string[];edge_ids:string[]}[];cycle_detected:boolean;truncated:boolean;message:string}
export const getKnowledgePath=(pid:string,source:string,target?:string,kind='connection',signal?:AbortSignal)=>apiGet<KnowledgePath>(`/api/projects/${encodeURIComponent(pid)}/knowledge/paths`,{source,target,kind,max_depth:4},signal);

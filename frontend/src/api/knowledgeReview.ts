import {apiGet,apiPost} from './client';
import type {KnowledgeNode,KnowledgeEdge} from './knowledge';

export type ReviewAction='verify'|'dispute'|'restore';
export const reviewKnowledge=(projectId:string,record:KnowledgeNode|KnowledgeEdge,action:ReviewAction,reason:string)=>apiPost<{status:string;record:KnowledgeNode|KnowledgeEdge}>(`/api/knowledge/records/${encodeURIComponent(record.id)}/quality`,{project_id:projectId,expected_version:record.version,action,reason});
export interface KnowledgeHistoryEntry {kind:string;created_at:string;snapshot:Record<string,unknown>}
export const getKnowledgeHistory=(projectId:string,recordId:string,signal?:AbortSignal)=>apiGet<{items:KnowledgeHistoryEntry[]}>(`/api/knowledge/records/${encodeURIComponent(recordId)}/history`,{project_id:projectId},signal);

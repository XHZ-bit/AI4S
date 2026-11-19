import {authenticatedFetch} from './session';
import type {KnowledgeNode,KnowledgeEdge,KnowledgeEvidence} from './knowledge';

export type LearningStatus='not_started'|'in_progress'|'understood'|'review';
export interface NodeProgress {node_id:string;status:LearningStatus;version:number;updated_at?:string;stale?:boolean}
export interface KnowledgePath {nodes:KnowledgeNode[];edges:KnowledgeEdge[];paths:{node_ids:string[];edge_ids:string[]}[];cycle_detected:boolean;truncated:boolean;message:string}
export type ResourceType='paper'|'tutorial'|'image'|'code'|'video'|'search';
export interface KnowledgeResource {id:string;title:string;url:string;type:ResourceType;reason?:string;origin?:string;access_status?:string;checked_at?:string;fetched?:boolean;embed_url?:string;source_id?:string;block_id?:string;evidence?:KnowledgeEvidence}
export interface NodeAnswer {answer:string;origin:'source'|'inference';citations:KnowledgeEvidence[];node_ids:string[];edge_ids:string[];model_used:boolean;warnings:string[]}
const BASE=import.meta.env.VITE_API_BASE??'';
const root=(project:string)=>`${BASE}/api/projects/${encodeURIComponent(project)}/knowledge`;
async function request<T>(url:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<T>{
 const response=await authenticatedFetch(url,{method,signal,headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){let message=`${response.status} ${response.statusText}`;try{const detail=(await response.json()).detail;message=typeof detail==='string'?detail:detail?.message||JSON.stringify(detail)}catch{/* Keep HTTP error. */}throw new Error(message)}
 return response.json() as Promise<T>;
}
const nodeRoot=(project:string,node:string)=>`${root(project)}/nodes/${encodeURIComponent(node)}`;
export const getNodeProgress=(project:string,node:string,signal?:AbortSignal)=>request<NodeProgress>(`${nodeRoot(project,node)}/progress`,'GET',undefined,signal);
export interface LearningExperienceEntry {kind:string;reason:string;run_id?:string;practice_id?:string}
export interface SavedLearningExperience {id:string;node_id:string;practice_id:string;content:string;origin:'user_saved_ai_feedback';created_at:string}
export interface NodeSummary {progress:NodeProgress;run_count:number;recent_runs:{id:string;practice_id:string;status:string;created_at:string}[];recommendation:string;suggested_node?:{id:string;label:string}|null;experience_entries?:LearningExperienceEntry[];saved_experiences?:SavedLearningExperience[];scope:string;explanation?:string;cached?:boolean;error?:string}
export const getNodeSummary=(project:string,node:string,signal?:AbortSignal)=>request<NodeSummary>(`${nodeRoot(project,node)}/summary`,'GET',undefined,signal);
export const explainNodeSummary=(project:string,node:string,signal?:AbortSignal)=>request<NodeSummary>(`${nodeRoot(project,node)}/summary`,'POST',undefined,signal);
export const getLearningProgress=(project:string,signal?:AbortSignal)=>request<{items:NodeProgress[]}>(`${root(project)}/progress`,'GET',undefined,signal);
export interface ProjectLearningSummary {items:{node_id:string;node_label:string;status:LearningStatus;run_count:number;recommendation:string;suggested_node?:{id:string;label:string}|null;experience_entries?:LearningExperienceEntry[];saved_experiences?:SavedLearningExperience[]}[];scope:string;truncated:boolean;explanation?:string;cached?:boolean;error?:string}
export const getProjectLearningSummary=(project:string,signal?:AbortSignal)=>request<ProjectLearningSummary>(`${root(project)}/progress/summary`,'GET',undefined,signal);
export const explainProjectLearningSummary=(project:string,signal?:AbortSignal)=>request<ProjectLearningSummary>(`${root(project)}/progress/summary`,'POST',undefined,signal);
export const saveNodeProgress=(project:string,node:string,status:LearningStatus,expected_version?:number,signal?:AbortSignal)=>request<NodeProgress>(`${nodeRoot(project,node)}/progress`,'PATCH',{status,expected_version},signal);
export const getNodeResources=(project:string,node:string,signal?:AbortSignal)=>request<{items:KnowledgeResource[]}>(`${nodeRoot(project,node)}/resources`,'GET',undefined,signal);
export const addNodeResource=(project:string,node:string,body:{title:string;url:string;type:ResourceType;reason?:string},signal?:AbortSignal)=>request<KnowledgeResource>(`${nodeRoot(project,node)}/resources`,'POST',body,signal);
export const getKnowledgePath=(project:string,params:{source:string;target?:string;kind?:'connection'|'prerequisites';max_depth?:number},signal?:AbortSignal)=>{const query=new URLSearchParams();Object.entries(params).forEach(([k,v])=>{if(v!==undefined)query.set(k,String(v))});return request<KnowledgePath>(`${root(project)}/paths?${query}`,'GET',undefined,signal)};
export const askKnowledgeNode=(project:string,node:string,question:string,signal?:AbortSignal)=>request<NodeAnswer>(`${nodeRoot(project,node)}/question`,'POST',{question},signal);

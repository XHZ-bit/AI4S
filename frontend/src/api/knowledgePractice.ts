import {authenticatedFetch} from './session';
import type {KnowledgeEvidence} from './knowledge';

export type PracticeDifficulty = 'foundation' | 'intermediate' | 'advanced';
export interface PracticeParameters {goal:string;difficulty:PracticeDifficulty;adjustment?:string;mapping_id?:string;mapping_revision?:number}
export interface PracticeRun {
 id:string;practice_id:string;status:'success'|'error'|'timeout'|'cancelled';output:string;code:string;
 input_json:string;elapsed_ms:number;checked:boolean;passed:boolean|null;created_at:string;
 origin:'browser_teaching_run';verification:'browser_reported_not_independently_verified';
 mapping_id?:string|null;mapping_revision?:number|null;prediction?:string;explanation?:string;
}
export interface PracticeVersion {id:string;title:string;goal:string;difficulty:PracticeDifficulty;status:string;node_version:number;revision:number;created_at:string}
export interface KnowledgePracticeArtifact extends PracticeParameters {
 id:string;project_id:string;node_id:string;node_label:string;node_version:number;source_version:string;
 title:string;prompt:string;status:'starter'|'ready'|'partial';origin:string;revision:number;created_at:string;
 starter_code:string;draft_code:string;test_code:string;reference_code:string;input_json:string;
 hints:string[];expected_behavior:string;learning_objectives:string[];simplifications:string[];
 evidence:KnowledgeEvidence[];errors:string[];usage:Record<string,number>;cached:boolean;stale:boolean;
 versions:PracticeVersion[];runs:PracticeRun[];
 mapping_snapshot?:PracticeMapping|null;mapping_stale?:boolean;
}
const BASE=import.meta.env.VITE_API_BASE??'';
const root=(project:string)=>`${BASE}/api/projects/${encodeURIComponent(project)}/knowledge`;
async function request<T>(url:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<T>{
 const response=await authenticatedFetch(url,{method,signal,headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){let message=`${response.status} ${response.statusText}`;try{const detail=(await response.json()).detail;message=typeof detail==='string'?detail:JSON.stringify(detail)}catch{/* Preserve HTTP error. */}throw new Error(message)}
 return response.json() as Promise<T>;
}
export const getNodePractice=(project:string,node:string,parameters?:PracticeParameters,signal?:AbortSignal)=>{
 const query=new URLSearchParams();if(parameters)Object.entries(parameters).forEach(([k,v])=>{if(v)query.set(k,String(v))});
 return request<KnowledgePracticeArtifact>(`${root(project)}/nodes/${encodeURIComponent(node)}/practice?${query}`,'GET',undefined,signal);
};
export const generateNodePractice=(project:string,node:string,body:PracticeParameters&{refresh?:boolean;previous_practice_id?:string},signal?:AbortSignal)=>request<KnowledgePracticeArtifact>(`${root(project)}/nodes/${encodeURIComponent(node)}/practice`,'POST',body,signal);
export const getPracticeVersion=(project:string,id:string,signal?:AbortSignal)=>request<KnowledgePracticeArtifact>(`${root(project)}/practice/${encodeURIComponent(id)}`,'GET',undefined,signal);
export const savePracticeDraft=(project:string,id:string,body:{expected_revision:number;code:string;input_json:string},signal?:AbortSignal)=>request<KnowledgePracticeArtifact>(`${root(project)}/practice/${encodeURIComponent(id)}`,'PATCH',body,signal);
export const recordPracticeRun=(project:string,id:string,body:Omit<PracticeRun,'id'|'practice_id'|'created_at'|'origin'|'verification'>,signal?:AbortSignal)=>request<PracticeRun>(`${root(project)}/practice/${encodeURIComponent(id)}/runs`,'POST',body,signal);
export const updatePracticeRunExplanation=(project:string,id:string,run:string,explanation:string)=>request<PracticeRun>(`${root(project)}/practice/${encodeURIComponent(id)}/runs/${encodeURIComponent(run)}`,'PATCH',{explanation});
export interface PracticeMapping {id:string;revision:number;paper_span:string;code_span:string;status:string;stale:boolean;implementation_kind?:string;paper_evidence?:KnowledgeEvidence;code_evidence?:KnowledgeEvidence}
export const getPracticeMappings=(project:string,node:string,signal?:AbortSignal)=>request<{items:PracticeMapping[]}>(`${root(project)}/nodes/${encodeURIComponent(node)}/implementations`,'GET',undefined,signal);
export const reviewPracticeCode=(project:string,id:string,body:{code:string;output:string},signal?:AbortSignal)=>request<{feedback:string}>(`${root(project)}/practice/${encodeURIComponent(id)}/review`,'POST',body,signal);
export const savePracticeExperience=(project:string,node:string,body:{content:string;practice_id:string},signal?:AbortSignal)=>request<{id:string;node_id:string;practice_id:string;content:string;origin:string;created_at:string}>(`${root(project)}/nodes/${encodeURIComponent(node)}/experiences`,'POST',body,signal);

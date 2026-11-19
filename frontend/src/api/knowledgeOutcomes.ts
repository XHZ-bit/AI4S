import {apiGet,apiPost} from './client';
import type {KnowledgeEvidence} from './knowledge';

export interface KnowledgeNoteContext {
 knowledge_node_id?:string;source_id?:string;block_id?:string;source_version?:string;node_version?:number;
 unresolved_questions?:string;content_origin?:'user'|'saved_ai_answer';
 evidence_references?:KnowledgeEvidence[];
}
export interface KnowledgeNote {id:string;version:number;title:string;body:string;kind:string;project_id:string;source_json:string;updated_at?:string;context?:KnowledgeNoteContext;stale?:boolean}
export interface OutcomeCatalog {
 node:{id:string;label:string;version:number};source:{id:string;title:string;version:string;removed:boolean};notes:KnowledgeNote[];
 evidence:{id:string;source_title:string;locator:{page?:number;heading?:string;path?:string};quote:string}[];
 lessons:{id:string;revision:number;goal:string;sections:Record<string,string>;stale:boolean}[];
 practices:{id:string;title:string;revision:number;runs:{id:string;status:string}[];stale:boolean}[];
 comparisons:{id:string;revision:number;stale:boolean;cells:{dimension:string;source_id:string;text:string}[]}[];
 mappings:{id:string;revision:number;paper_span:string;code_span:string;status:string;stale:boolean}[];
}
export interface OutcomeSelection {note_ids:string[];evidence_ids:string[];learning_sections:{artifact_id:string;revision:number;section:string}[];practice_ids:string[];comparison_cells:{comparison_id:string;revision:number;dimension:string;source_id:string}[];mappings:{id:string;revision:number}[]}
export interface OutcomePreview {filename:string;markdown:string;selected_count:number}
const root=(project:string,node:string)=>`/api/workbench/projects/${encodeURIComponent(project)}/nodes/${encodeURIComponent(node)}/outcomes`;
export const listNodeNotes=(project:string,node:string,signal?:AbortSignal)=>apiGet<{items:KnowledgeNote[]}>('/api/workbench/records',{project_id:project,knowledge_node_id:node},signal);
export const saveNodeNote=(note:{id:string;version:number;title:string;body:string;project_id:string;knowledge_node_id:string;unresolved_questions:string;content_origin:'user'|'saved_ai_answer';source_id?:string;block_id?:string;source_version?:string;node_version?:number;evidence_references?:KnowledgeEvidence[]})=>apiPost<KnowledgeNote>('/api/workbench/records',{...note,kind:'note'});
export const getNodeOutcomes=(project:string,node:string,signal?:AbortSignal)=>apiGet<OutcomeCatalog>(root(project,node),undefined,signal);
export const previewNodeOutcomes=(project:string,node:string,selection:OutcomeSelection)=>apiPost<OutcomePreview>(root(project,node)+'/preview',selection);
export function noteContext(note?:KnowledgeNote):KnowledgeNoteContext {if(note?.context)return note.context;try{return JSON.parse(note?.source_json||'{}')}catch{return {}}}

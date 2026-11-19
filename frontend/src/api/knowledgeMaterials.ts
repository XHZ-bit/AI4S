import {apiGet,apiPatch,apiPost} from './client';
import {authenticatedFetch} from './session';
import type {KnowledgeNode,KnowledgeSource,SourceKind} from './knowledge';

export interface MaterialSource {id:string;title:string;version:string;filename:string;kind:SourceKind;media_type:string;removed?:boolean}
export interface NodeMaterial {
 id:string;project_id:string;node_id:string;source_id:string;revision:number;note:string;removed:boolean;
 created_at:string;updated_at:string;reviewed_by:string;
 source_snapshot:MaterialSource;current_source:MaterialSource|null;
 source_changed:boolean;source_missing:boolean;original_url:string|null;
}
const root=(project:string,node:string)=>`/api/projects/${encodeURIComponent(project)}/knowledge/nodes/${encodeURIComponent(node)}/materials`;
export const getNodeMaterials=(project:string,node:string,signal?:AbortSignal)=>apiGet<{items:NodeMaterial[]}>(root(project,node),undefined,signal);
export const bindNodeMaterial=(project:string,node:string,source:string,note='')=>apiPost<{item:NodeMaterial}>(root(project,node),{source_id:source,note});
export const updateNodeMaterial=(project:string,node:string,id:string,body:{expected_revision:number;note?:string;removed?:boolean})=>apiPatch<{item:NodeMaterial}>(root(project,node)+'/'+encodeURIComponent(id),body);
export async function uploadNodeMaterial(project:string,node:string,file:File,note=''){
 const form=new FormData();form.append('file',file);if(note.trim())form.append('note',note.trim());
 const response=await authenticatedFetch((import.meta.env.VITE_API_BASE||'')+root(project,node)+'/upload',{method:'POST',body:form});
 if(!response.ok){let message='资料未导入，请重试';let savedSource:MaterialSource|undefined;try{const result=await response.json();message=typeof result.detail==='string'?result.detail:result.detail?.message||message;savedSource=result.detail?.saved_source}catch{}throw Object.assign(new Error(message),{status:response.status,savedSource})}
 return response.json() as Promise<{item:NodeMaterial;source:KnowledgeSource;reading_status?:'ready'|'original_only'}>;
}
export type ManualNodeKind='concept'|'method'|'formula'|'experiment'|'finding';
export const createManualNode=(project:string,body:{label:string;summary:string;kind:ManualNodeKind})=>apiPost<{node:KnowledgeNode}>(`/api/projects/${encodeURIComponent(project)}/knowledge/nodes`,body);

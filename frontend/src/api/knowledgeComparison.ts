import {apiGet,apiPatch,apiPost} from './client';
import type {KnowledgeComparison,KnowledgeEvidence} from './knowledge';

export type ComparisonTemplate='method'|'study';
export const comparisonTemplates:Record<ComparisonTemplate,{label:string;dimensions:string[]}>= {
 method:{label:'方法机制',dimensions:['研究问题','方法与模块划分','信息路径与机制','输入与观测','输出与执行方式','训练目标与额外成本','实验条件与结果','适用范围与局限']},
 study:{label:'研究设计与发现',dimensions:['研究问题','样本与研究对象','研究设计与实验条件','测量指标与时间','主要发现','适用范围与局限']},
};
export type ComparisonCell=KnowledgeComparison['rows'][number]['values'][number]&{
 evidence_snapshot?:KnowledgeEvidence[];reviewed?:boolean;review_stale?:boolean;reviewed_by?:string;reviewed_at?:string;
};
export type ComparisonSelection={dimension:string;source_id:string};
export interface ComparisonOutcome {
 id:string;title:string;markdown:string;created_at:string;comparison_revision:number;stale:boolean;
 question:string;interpretation:string;unresolved:string;
 cells:(ComparisonCell&{dimension:string;evidence:KnowledgeEvidence[]})[];
 comparison_changed?:boolean;source_changes?:{source_id:string;title:string;reason:string}[];
}
export interface ComparisonOutcomeRequest {
 expected_revision:number;selections:ComparisonSelection[];question:string;interpretation:string;unresolved:string;
}
const root=(project:string,id:string)=>`/api/projects/${encodeURIComponent(project)}/knowledge/comparisons/${encodeURIComponent(id)}`;
export const comparisonTemplate=(value:KnowledgeComparison):ComparisonTemplate=>
 (value as KnowledgeComparison&{template?:ComparisonTemplate}).template||
 (JSON.stringify(value.dimensions||value.rows.map(r=>r.dimension))===JSON.stringify(comparisonTemplates.study.dimensions)?'study':'method');
export const listComparisonEvidence=(project:string,id:string,source:string,signal?:AbortSignal)=>
 apiGet<{items:KnowledgeEvidence[]}>(root(project,id)+'/evidence',{source_id:source},signal);
export const reviseComparisonCell=(project:string,id:string,body:{source_ids:string[];focus_node_ids?:string[];dimensions?:string[];template?:ComparisonTemplate;expected_revision:number;dimension:string;source_id:string;text:string;evidence_ids:string[];reviewed:boolean})=>
 apiPatch<KnowledgeComparison>(root(project,id),body);
export const previewComparisonOutcome=(project:string,id:string,body:ComparisonOutcomeRequest)=>
 apiPost<ComparisonOutcome>(root(project,id)+'/outcomes/preview',body);
export const saveComparisonOutcome=(project:string,id:string,body:ComparisonOutcomeRequest)=>
 apiPost<ComparisonOutcome>(root(project,id)+'/outcomes',body);
export const listComparisonOutcomes=(project:string,id:string,signal?:AbortSignal)=>
 apiGet<{items:ComparisonOutcome[]}>(root(project,id)+'/outcomes',undefined,signal);

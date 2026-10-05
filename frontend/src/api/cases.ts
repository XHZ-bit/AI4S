import { apiGet, apiPost, apiPatch } from "./client";
export const caseBase = (id: string) => `/api/cases/${encodeURIComponent(id)}`;
export interface CaseInfo {
  id: string; version: string; title: string; status: string; notice: string;
  commit: string; repository: string; paper_url: string; paper_notice: string;
  steps: {id:string; title:string; minutes:number; criterion:string; body:string}[];
  sources: {path:string; sha256:string; text:string; url:string}[];
  mappings: {title:string; source:number; line:number; url:string; explanation:string}[];
  questions: {id:string; step:string; question:string; options:string[]; source:number}[];
  troubleshooting: {id:string; title:string; action:string}[];
}
export interface Profile {goal:string; system:string; compute:string}
export interface CaseSession {
  id:string; version:number; case_version:string; stale:boolean;
  state:{current_step:string; read_steps:string[]; profile:Profile; answers:Record<string,{choice:number; correct:boolean; explanation:string; attempts:number; review_step:string}>};
  runs:{id:number; created_at:string; report:{passed:boolean; notice:string; verification:string; checks:{id:string; label:string; passed:boolean}[]}}[];
}
export const getCase = (id:string, signal?:AbortSignal) => apiGet<CaseInfo>(caseBase(id),undefined,signal);
export const getCaseSession = (id:string,sid:string,signal?:AbortSignal) => apiGet<CaseSession>(`${caseBase(id)}/sessions/${encodeURIComponent(sid)}`,undefined,signal);
export const newCaseSession = (id:string) => apiPost<CaseSession>(`${caseBase(id)}/sessions`);
export const patchCaseSession = (id:string,sid:string,body:unknown) => apiPatch<CaseSession>(`${caseBase(id)}/sessions/${sid}`,body);
export const answerCaseQuestion = (id:string,sid:string,body:unknown) => apiPost<CaseSession>(`${caseBase(id)}/sessions/${sid}/answers`,body);
export const importCaseRun = (id:string,sid:string,body:unknown) => apiPost<CaseSession>(`${caseBase(id)}/sessions/${sid}/runs`,body);

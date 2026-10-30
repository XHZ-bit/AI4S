import { apiGet } from "./client";

export interface AccessLink {url:string;label:string;origin:string;verified_at?:string|null;note?:string}
export interface GraphNode { uid: string; name: string; type: string; access_links?:AccessLink[];sources?:{paper_uid:string;paper_title?:string;passage_id?:string|null}[];is_match?:boolean; }
export interface GraphLink { source: string; target: string; rel_type: string; quality_status?: string; passage_id?: string | null; paper_uid?: string; }
export interface GraphView { nodes: GraphNode[]; links: GraphLink[]; backend?: string; notice?: string; truncated?: boolean; matched_count?:number;context_count?:number;shown_matches?:number; }

export const getContext = (q:string,type?:string,project_id?:string,seed?:string)=>apiGet<GraphView>('/api/graph/context',{q,type,project_id,seed,limit:50});

export const searchNodes = (q: string, type?: string) =>
  apiGet<{ items: GraphNode[] }>("/api/graph/nodes", { q, type }).then(r => r.items);
export const getNeighbors = (uid: string) =>
  apiGet<GraphView>(`/api/graph/neighbors/${encodeURIComponent(uid)}`);

export const getOverview = () =>
  apiGet<GraphView>("/api/graph/overview");

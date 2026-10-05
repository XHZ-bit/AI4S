import { apiGet } from "./client";

export interface GraphNode { uid: string; name: string; type: string; }
export interface GraphLink { source: string; target: string; rel_type: string; }

export const searchNodes = (q: string, type?: string) =>
  apiGet<{ items: GraphNode[] }>("/api/graph/nodes", { q, type }).then(r => r.items);
export const getNeighbors = (uid: string) =>
  apiGet<{ nodes: GraphNode[]; links: GraphLink[] }>(`/api/graph/neighbors/${uid}`);

export const getOverview = () =>
  apiGet<{ nodes: GraphNode[]; links: GraphLink[] }>("/api/graph/overview");

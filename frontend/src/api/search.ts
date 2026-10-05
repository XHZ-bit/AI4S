import { apiGet } from "./client";

export type SearchResult = { uid: string; score: number };
export const semanticSearch = (q: string, limit = 10) =>
  apiGet<{ items: SearchResult[] }>("/api/search", { q, limit });
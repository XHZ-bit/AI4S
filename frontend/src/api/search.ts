import { apiGet } from "./client";

export type SearchResult = { uid: string; score: number };
export const semanticSearch = (q: string, limit = 10) =>
  apiGet<{ items: SearchResult[] }>("/api/search", { q, limit });

export interface PaperSearchResult {
  uid: string;
  title: string;
  snippet: string;
  score: number | null;
  year?: number | null;
  source?: string | null;
  hit_reason?: string;
  passage_id?: string | null;
  document_id?: string | null;
  document_version?: string | null;
  page?: number | null;
  /** A continuous, unchanged substring of the saved passage, when available. */
  quote?: string | null;
}

export interface PaperSearchResponse {
  items: PaperSearchResult[];
  mode: "keyword" | "semantic" | "hybrid";
  notice?: string;
}

export const searchPapers = (q: string, limit = 10, signal?: AbortSignal) =>
  apiGet<PaperSearchResponse>("/api/search/v2", { q, limit }, signal);

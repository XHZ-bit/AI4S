import { apiGet } from "./client";

export interface QuickPaper {
  uid: string;
  title: string;
  year?: number | null;
}

// The metadata endpoint is SQLite-only. Typing in a launcher must never start
// an embedding/model request via the optional semantic search endpoint.
export const quickFindPapers = (q: string, signal?: AbortSignal) =>
  apiGet<{ total: number; items: QuickPaper[] }>("/api/papers", { q, limit: 6, offset: 0 }, signal);

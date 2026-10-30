import { apiGet, apiPatch } from "./client";

export type LibraryFilter = "all" | "starred" | "read_later";

export interface LibraryPaper {
  uid: string;
  title: string;
  abstract: string;
  authors: string[];
  year: number | null;
  source: string;
  parse_status: string;
  created_at: string;
  starred: boolean;
  read_later: boolean;
  library_updated_at: string | null;
}

export interface LibraryPage { total: number; items: LibraryPaper[] }

export function listLibraryPapers(
  options: { filter?: LibraryFilter; q?: string; parse_status?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) {
  return apiGet<LibraryPage>("/api/library/papers", { filter: "all", limit: 20, offset: 0, ...options }, signal);
}

export const updateLibraryPaper = (uid: string, changes: Partial<Pick<LibraryPaper, "starred" | "read_later">>) =>
  apiPatch<LibraryPaper>(`/api/library/papers/${encodeURIComponent(uid)}`, changes);

import { apiGet } from "./client";
import { authenticatedFetch } from "./session";

export interface ReadingPosition {
  paper_uid: string;
  document_id: string;
  document_version: string;
  page: number;
  page_count: number;
  updated_at: string;
}
export interface PositionResponse { position: ReadingPosition | null }
const endpoint = (uid: string) => `/api/papers/${encodeURIComponent(uid)}/reading-position`;

export const getReadingPosition = (uid: string, documentId: string, signal?: AbortSignal) =>
  apiGet<PositionResponse>(endpoint(uid), { document_id: documentId }, signal);

export async function saveReadingPosition(uid: string, documentId: string, page: number, signal?: AbortSignal): Promise<PositionResponse> {
  const response = await authenticatedFetch(`${import.meta.env.VITE_API_BASE ?? ""}${endpoint(uid)}`, {
    method: "PUT", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page }),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); if (typeof body.detail === "string") detail = body.detail; } catch { /* Keep the HTTP status for non-JSON responses. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<PositionResponse>;
}

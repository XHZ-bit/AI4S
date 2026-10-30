import { apiGet, apiPost } from "./client";
import { authenticatedFetch } from "./session";

export type TaskStatus<T = unknown> = {
  id: number;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
  error?: string | null;
  result?: T | null;
};

export const getPaper = (uid: string) => apiGet<any>(`/api/papers/${uid}`);
export const listPapers = (limit = 20, offset = 0) => apiGet<{ total: number; items: any[] }>("/api/papers", { limit, offset });
export const extractPaper = (uid: string) => apiPost<any>(`/api/papers/${uid}/extract`);
export const startExtract = (uid: string) => apiPost<{ task_id: number; status: string }>(`/api/papers/${uid}/extract-async`);
export const getExtractStatus = (taskId: number) => apiGet<TaskStatus<Record<string, number>>>(`/api/extract/${taskId}`);
export const collect = (body: { keywords: string[]; categories: string[]; start_year: number; max_results: number; include_citations?: boolean }) =>
  apiPost<{ task_id: number }>("/api/collect", body);
export const getCollectStatus = (taskId: number) => apiGet<TaskStatus>(`/api/collect/${taskId}`);

export interface UploadReceipt { uid: string; task_id: number; parse_status: string }
export interface UploadFailure extends Error { status?: number; saved?: boolean; uid?: string; parse_status?: string; retryable?: boolean }
export const getUploadTask = (taskId: number, signal?: AbortSignal) =>
  apiGet<TaskStatus<{ warnings?: unknown[] }>>(`/api/learning/tasks/${taskId}`, undefined, signal);
export const reparsePaper = (uid: string, signal?: AbortSignal) =>
  apiPost<{ task_id: number }>(`/api/papers/${encodeURIComponent(uid)}/parse`, undefined, signal);

export const uploadPdf = async (file: File, signal?: AbortSignal): Promise<UploadReceipt> => {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await authenticatedFetch(`${import.meta.env.VITE_API_BASE ?? ""}/api/papers/upload-async`, {
    method: "POST",
    body: fd,
    signal,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    let saved: Partial<UploadFailure> = {};
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      saved = { saved: body.saved === true, uid: typeof body.uid === "string" ? body.uid : undefined,
        parse_status: typeof body.parse_status === "string" ? body.parse_status : undefined, retryable: body.retryable === true };
    } catch { /* response is not JSON */ }
    throw Object.assign(new Error(detail || String(resp.status)), { status: resp.status, ...saved });
  }
  return resp.json();
};

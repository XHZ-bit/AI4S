import { apiGet, apiPost } from "./client";

export type TaskStatus<T = unknown> = {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  error?: string | null;
  result?: T | null;
};

export const getPaper = (uid: string) => apiGet<any>(`/api/papers/${uid}`);
export const listPapers = (limit = 20, offset = 0) => apiGet<{ total: number; items: any[] }>("/api/papers", { limit, offset });
export const extractPaper = (uid: string) => apiPost<any>(`/api/papers/${uid}/extract`);
export const startExtract = (uid: string) => apiPost<{ task_id: number; status: string }>(`/api/papers/${uid}/extract-async`);
export const getExtractStatus = (taskId: number) => apiGet<TaskStatus<Record<string, number>>>(`/api/extract/${taskId}`);
export const collect = (body: { keywords: string[]; categories: string[]; start_year: number; max_results: number }) =>
  apiPost<{ task_id: number }>("/api/collect", body);
export const getCollectStatus = (taskId: number) => apiGet<TaskStatus>(`/api/collect/${taskId}`);

export const uploadPdf = async (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(`${import.meta.env.VITE_API_BASE ?? ""}/api/papers/upload-async`, {
    method: "POST",
    body: fd,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try { const body = await resp.json(); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail); } catch { /* response is not JSON */ }
    throw new Error(detail || String(resp.status));
  }
  return resp.json();
};
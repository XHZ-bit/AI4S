import { apiGet, apiPost } from "./client";
export const reviewQueue = (kind?: string) => apiGet<{ items: any[] }>("/api/review/queue", { kind });
export const decide = (pid: number, action: string, payload?: any) => apiPost<{ status: string }>(`/api/review/${pid}/decision`, { action, payload });

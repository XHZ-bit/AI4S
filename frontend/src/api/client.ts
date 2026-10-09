const BASE = import.meta.env.VITE_API_BASE ?? "";

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    // FastAPI 422 校验错误时 detail 是数组
    return detail
      .map(d => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d)))
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return detail ? String(detail) : fallback;
}

async function errorFrom(response: Response): Promise<Error> {
  try {
    const body = await response.json();
    return Object.assign(new Error(detailToMessage(body.detail, `${response.status} ${response.statusText}`)), { status: response.status });
  } catch {
    return new Error(`${response.status} ${response.statusText}`);
  }
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) for (const [k, v] of Object.entries(params)) if (v != null) url.searchParams.set(k, String(v));
  const resp = await fetch(url, { signal });
  if (!resp.ok) throw await errorFrom(resp);
  return resp.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(BASE + path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!resp.ok) throw await errorFrom(resp);
  if (!/\/assistant\/|\/scenarios\//.test(path)) window.dispatchEvent(new CustomEvent("atlas:data-change", { detail: { path } }));
  return resp.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await errorFrom(resp);
  window.dispatchEvent(new CustomEvent("atlas:data-change", { detail: { path } }));
  return resp.json() as Promise<T>;
}

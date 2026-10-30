import { afterEach, test, vi } from "vitest";
import { listLibraryPapers, updateLibraryPaper } from "../api/library";
import { setCsrfToken } from "../api/session";

afterEach(() => { setCsrfToken(); });

test("library filters and marker patches use authenticated existing API transport", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) });
  const controller = new AbortController();
  await listLibraryPapers({ filter: "starred", q: "异常检测", parse_status: "parsed", limit: 5, offset: 10 }, controller.signal);
  const [input, options] = vi.mocked(fetch).mock.calls[0];
  const url = new URL(String(input));
  expect(url.pathname).toBe("/api/library/papers");
  expect(Object.fromEntries(url.searchParams)).toEqual({ filter: "starred", q: "异常检测", parse_status: "parsed", limit: "5", offset: "10" });
  expect(options?.signal).toBe(controller.signal);
  expect(options?.credentials).toBe("same-origin");
  setCsrfToken("test-library-csrf");
  await updateLibraryPaper("paper:1", { read_later: false });
  const [patch, patchOptions] = vi.mocked(fetch).mock.calls[1];
  expect(String(patch)).toBe("/api/library/papers/paper%3A1");
  expect(patchOptions?.method).toBe("PATCH");
  expect(patchOptions?.body).toBe(JSON.stringify({ read_later: false }));
  expect(new Headers(patchOptions?.headers).get("X-Atlas-CSRF")).toBe("test-library-csrf");
});

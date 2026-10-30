import { expect, test, vi } from "vitest";
import { searchPapers } from "../api/search";

test("v2 search preserves its query, limit and cancellation signal", async () => {
  const result = { mode: "keyword", items: [] };
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => result });
  const controller = new AbortController();
  await expect(searchPapers("异常 检测", 5, controller.signal)).resolves.toEqual(result);
  const [input, options] = vi.mocked(fetch).mock.calls[0];
  const url = new URL(String(input));
  expect(url.pathname).toBe("/api/search/v2");
  expect(url.searchParams.get("q")).toBe("异常 检测");
  expect(url.searchParams.get("limit")).toBe("5");
  expect(options?.signal).toBe(controller.signal);
});

import { expect, test, vi } from "vitest";
import { quickFindPapers } from "../api/quickFind";

test("launcher typing uses the local metadata endpoint and passes cancellation", async () => {
  const controller = new AbortController();
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ total: 0, items: [] }) });
  await quickFindPapers("机器人 & policy", controller.signal);
  const [target, options] = vi.mocked(fetch).mock.calls[0];
  const url = new URL(String(target), "http://localhost");
  expect(url.pathname).toBe("/api/papers");
  expect(url.searchParams.get("q")).toBe("机器人 & policy");
  expect(url.searchParams.get("limit")).toBe("6");
  expect(options?.signal).toBe(controller.signal);
});

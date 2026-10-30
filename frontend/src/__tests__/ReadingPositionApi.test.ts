import { vi } from "vitest";
import { getReadingPosition, saveReadingPosition } from "../api/readingPosition";
import { setCsrfToken } from "../api/session";

afterEach(() => { setCsrfToken(); vi.unstubAllGlobals(); });
test("version-specific read and authenticated PUT preserve encoding, CSRF and cancellation", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ position: null }) });
  vi.stubGlobal("fetch", fetch); setCsrfToken("test-csrf");
  const controller = new AbortController();
  await getReadingPosition("paper:one", "document/id", controller.signal);
  const url = new URL(String(fetch.mock.calls[0][0]));
  expect(url.pathname).toBe("/api/papers/paper%3Aone/reading-position");
  expect(url.searchParams.get("document_id")).toBe("document/id");
  await saveReadingPosition("paper:one", "document/id", 2, controller.signal);
  const options = fetch.mock.calls[1][1];
  expect(options.method).toBe("PUT"); expect(options.credentials).toBe("same-origin");
  expect(options.signal).toBe(controller.signal);
  expect(new Headers(options.headers).get("X-Atlas-CSRF")).toBe("test-csrf");
  expect(JSON.parse(options.body)).toEqual({ document_id: "document/id", page: 2 });
});

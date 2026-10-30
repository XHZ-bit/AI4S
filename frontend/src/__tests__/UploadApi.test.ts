import { test, vi } from "vitest";
import { getUploadTask, reparsePaper, uploadPdf } from "../api/papers";

test("upload, task polling and reparse retain cancellation and existing authenticated transport", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ uid: "paper", task_id: 1, parse_status: "queued" }) });
  const controller = new AbortController();
  await uploadPdf(new File(["PDF"], "one.pdf"), controller.signal);
  const [upload, options] = vi.mocked(fetch).mock.calls[0];
  expect(String(upload)).toBe("/api/papers/upload-async");
  expect(options?.signal).toBe(controller.signal);
  expect(options?.credentials).toBe("same-origin");
  expect(options?.body instanceof FormData).toBe(true);
  await getUploadTask(1, controller.signal);
  const [poll, pollOptions] = vi.mocked(fetch).mock.calls[1];
  expect(new URL(String(poll)).pathname).toBe("/api/learning/tasks/1");
  expect(pollOptions?.signal).toBe(controller.signal);
  await reparsePaper("paper:one", controller.signal);
  expect(vi.mocked(fetch).mock.calls[2][0]).toBe("/api/papers/paper%3Aone/parse");
  expect(vi.mocked(fetch).mock.calls[2][1]?.signal).toBe(controller.signal);
});

test("upload errors retain saved receipt metadata and the server's human-readable detail", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 429, statusText: "Too Many Requests",
    json: async () => ({ detail: "原文已保存，尚未排入解析", saved: true, uid: "saved", parse_status: "not_queued", retryable: true }) });
  await expect(uploadPdf(new File(["PDF"], "one.pdf"))).rejects.toMatchObject({ message: "原文已保存，尚未排入解析", status: 429, saved: true, uid: "saved", parse_status: "not_queued", retryable: true });
});

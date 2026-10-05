import { beforeEach, describe, expect, test, vi } from "vitest";
import { ProjectApiError, getProject, updateProject } from "../../api/projects";
import { project } from "./fixtures";

describe("research project API status preservation", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  test("keeps structured 409 metadata for local conflict handling", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({ detail: { code: "version_conflict", message: "项目已更新", retryable: true, fields: {}, current_version: 4, request_id: null } }),
    });
    const error = await updateProject(project.id, { expected_version: 3, title: "本地草稿", research_question: null, status: null, constraints: null }).catch(caught => caught);
    expect(error).toBeInstanceOf(ProjectApiError);
    expect(error).toMatchObject({ status: 409, code: "version_conflict", currentVersion: 4, retryable: true });
  });

  test("supports abort signals when refreshing saved content", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => project });
    const controller = new AbortController();
    await expect(getProject(project.id, controller.signal)).resolves.toEqual(project);
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.any(URL), expect.objectContaining({ signal: controller.signal }));
  });
});

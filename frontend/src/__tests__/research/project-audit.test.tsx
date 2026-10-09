import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import ProjectAuditPanel from "../../components/research/ProjectAuditPanel";

const api = vi.hoisted(() => ({ getProjectAudit: vi.fn() }));
vi.mock("../../api/projects", () => api);

test("automatic audit shows source impact and refreshes after a data change", async () => {
  api.getProjectAudit.mockResolvedValue({
    contract_version: "project-audit-v1", rule_version: "project-audit-1",
    project_id: "project-1", input_fingerprint: "abc123456789def", notice: "自动核查，不证明结论。",
    summary: { blocking: 1, warning: 0, notice: 0 },
    issues: [{ id: "issue-1", code: "quote_mismatch", severity: "blocking", title: "引文与片段文字不一致",
      detail: "证据 e1 无法定位", fact_ids: ["fact-1"], evidence_ids: ["e1"], paper_uids: ["paper-1"],
      affected_plan_ids: ["plan-1"], affected_snapshot_ids: ["snapshot-1"] }],
  });
  render(<MemoryRouter><ProjectAuditPanel projectId="project-1" /></MemoryRouter>);
  expect(await screen.findByText("引文与片段文字不一致")).toBeTruthy();
  expect(screen.getByText("影响方案 1 项")).toBeTruthy();
  expect(screen.getByText("影响快照 1 项")).toBeTruthy();
  fireEvent(window, new Event("atlas:data-change"));
  await waitFor(() => expect(api.getProjectAudit).toHaveBeenCalledTimes(2));
  const refresh = await screen.findByRole("button", { name: "重新核查" });
  fireEvent.click(refresh);
  await waitFor(() => expect(api.getProjectAudit).toHaveBeenCalledTimes(3));
});

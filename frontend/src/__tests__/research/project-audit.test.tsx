import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import ProjectAuditPanel from "../../components/research/ProjectAuditPanel";

const api = vi.hoisted(() => ({ getProjectAudit: vi.fn(), getProjectImpact: vi.fn(),
  getImpactCheckpoint: vi.fn(), getImpactChanges: vi.fn(), saveImpactCheckpoint: vi.fn() }));
vi.mock("../../api/projects", () => api);

test("automatic audit shows source impact and refreshes after a data change", async () => {
  api.getImpactCheckpoint.mockResolvedValue({ checkpoint: null });
  api.getProjectImpact.mockResolvedValue({
    input_fingerprint: "abc123456789def", issues: [{ issue_id: "issue-1", affected: [
      { kind: "activity", id: "project:snapshot-1:step-1", url: "/workflow", reason: "source changed" },
    ] }],
  });
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
  expect(screen.getByText(/step-1 · 查看依据/)).toBeTruthy();
  fireEvent(window, new Event("atlas:data-change"));
  await waitFor(() => expect(api.getProjectAudit).toHaveBeenCalledTimes(2));
  const refresh = await screen.findByRole("button", { name: "重新核查" });
  fireEvent.click(refresh);
  await waitFor(() => expect(api.getProjectAudit).toHaveBeenCalledTimes(3));
});

test("records a baseline and shows source changes", async () => {
  vi.clearAllMocks();
  api.getProjectAudit.mockResolvedValue({ contract_version: "project-audit-v1", rule_version: "rule-1",
    project_id: "project-2", input_fingerprint: "a".repeat(64), notice: "机器检查",
    summary: { blocking: 0, warning: 0, notice: 0 }, issues: [] });
  api.getProjectImpact.mockResolvedValue({ input_fingerprint: "a".repeat(64), issues: [] });
  const checkpoint = { checkpoint_id: "baseline-1", project_id: "project-2",
    input_fingerprint: "a".repeat(64), created_at: "2026-10-10" };
  api.getImpactCheckpoint.mockResolvedValueOnce({ checkpoint: null }).mockResolvedValue({ checkpoint });
  api.saveImpactCheckpoint.mockResolvedValue(checkpoint);
  api.getImpactChanges.mockResolvedValue({ contract_version: "project-impact-changes-v1",
    project_id: "project-2", checkpoint_id: "baseline-1", baseline_created_at: "2026-10-10",
    baseline_fingerprint: "a".repeat(64), current_fingerprint: "b".repeat(64),
    added: [{ id: "issue-new", title: "引文变化", detail: "原文已变", affected_plan_ids: ["p1"],
      affected_snapshot_ids: ["s1"] }], resolved: [], changed: [], notice: "仅比较问题" });
  render(<MemoryRouter><ProjectAuditPanel projectId="project-2" /></MemoryRouter>);
  const button = await screen.findByRole("button", { name: "记录当前核查基线" });
  await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
  fireEvent.click(button);
  await waitFor(() => expect(api.saveImpactCheckpoint).toHaveBeenCalledWith("project-2", "a".repeat(64)));
  expect(await screen.findByText(/新增问题 1/)).toBeTruthy();
  expect(screen.getByText(/引文变化/)).toBeTruthy();
});

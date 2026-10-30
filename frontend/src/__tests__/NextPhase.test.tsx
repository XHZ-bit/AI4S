import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import WorkflowHub from "../pages/WorkflowHub";

vi.mock("../api/client", () => ({ apiGet: vi.fn(async () => ({ items: [] })) }));
vi.mock("../api/workflow", () => ({
  workflowOverview: vi.fn(async () => ({ counts: { pending: 0, in_progress: 0, completed: 0, needs_review: 0 }, total: 0, snapshot_required: 0, next: [] })),
  workflowActivities: vi.fn(async () => ({ items: [], total: 0, offset: 0, limit: 50 })),
  listMastery: vi.fn(async () => ({ items: [] })),
  workflowRecommendations: vi.fn(async () => ({ contract_version: "workflow-recommendations-v1", total: 1, input_fingerprint: "f", truncated: false, ranking_rule_version: "workflow-priority-1", notice: "只反映固定练习结果。", items: [
    { id: "review:practice:x", kind: "practice_review", title: "复习并重试", reason: "未通过固定练习", url: "/cases/diffusion-policy-intro", source_ids: ["practice:x"], rank: 1, priority_score: 80, priority_reason: "最近一次固定检查未通过", related_activity_count: 1 },
  ] })),
}));

test("workflow shows an evidence-bound review action without changing mastery", async () => {
  render(<MemoryRouter><WorkflowHub /></MemoryRouter>);
  const link = await screen.findByRole("link", { name: "复习并重试" });
  expect(link.getAttribute("href")).toBe("/cases/diffusion-policy-intro");
  expect(screen.getByText(/未通过固定练习/)).toBeTruthy();
  expect(screen.getByText(/规则分 80/)).toBeTruthy();
  expect(screen.getByText(/只反映固定练习结果/)).toBeTruthy();
});

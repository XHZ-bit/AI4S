import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import ResearchPrintPage from "../../pages/research/ResearchPrintPage";
import { plan, project, snapshot } from "./fixtures";

const api = vi.hoisted(() => ({ getProjectSnapshot: vi.fn() }));
vi.mock("../../api/projects", () => api);

beforeEach(() => { localStorage.clear(); api.getProjectSnapshot.mockReset().mockResolvedValue(snapshot); });

test("saved snapshot print includes review and unknown states", async () => {
  render(<MemoryRouter initialEntries={[`/research/${project.id}/print/${snapshot.id}`]}><Routes><Route path="/research/:projectId/print/:snapshotId" element={<ResearchPrintPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("不可变快照 v1")).toBeTruthy();
  expect(screen.getByText("待复核")).toBeTruthy();
  expect(screen.getByText("真实显存未知")).toBeTruthy();
  expect(screen.getByText("project_constraints_changed")).toBeTruthy();
});

test("local draft print is visibly marked unsaved", async () => {
  localStorage.setItem(`research-atlas:plan-draft:${project.id}:${plan.id}`, JSON.stringify({ ...plan, status: "draft" }));
  render(<MemoryRouter initialEntries={[`/research/${project.id}/print/draft?plan_id=${plan.id}`]}><Routes><Route path="/research/:projectId/print/:snapshotId" element={<ResearchPrintPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("未保存的本地草稿")).toBeTruthy();
  expect(screen.getByText("此打印件来自未保存草稿")).toBeTruthy();
  expect(screen.getByText("草稿状态")).toBeTruthy();
});

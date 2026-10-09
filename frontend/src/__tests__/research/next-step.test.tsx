import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";
import ResearchProjectPage from "../../pages/research/ResearchProjectPage";
import { project } from "./fixtures";

vi.mock("../../api/projects", () => ({ getProject: vi.fn(async () => project) }));
vi.mock("../../components/research/EvidencePanel", () => ({ default: () => <div>evidence-panel</div> }));
vi.mock("../../components/research/ComparisonPanel", () => ({ default: () => <div>comparison-panel</div> }));
vi.mock("../../components/research/PlansPanel", () => ({ default: () => <div>plans-panel</div> }));
vi.mock("../../components/research/ProjectSettingsPanel", () => ({ default: () => <div>settings-panel</div> }));

test("next actions explain manual review and navigate without claiming completion", async () => {
  render(<MemoryRouter initialEntries={["/research/project-1?tab=evidence"]}><Routes><Route path="/research/:projectId" element={<ResearchProjectPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("第 1 步：关联资料并确认事实")).toBeTruthy();
  fireEvent.click(screen.getByText("前往条件比较"));
  expect(await screen.findByText("第 2 步：比较条件，再由你选择路线")).toBeTruthy();
  fireEvent.click(screen.getByText("前往方案编辑"));
  expect(await screen.findByText("第 3 步：审核方案，保存并冻结版本")).toBeTruthy();
  expect(screen.getByText(/模型建议不是实验结果/)).toBeTruthy();
  fireEvent.click(screen.getByText("返回核对证据"));
  expect(await screen.findByText("第 1 步：关联资料并确认事实")).toBeTruthy();
});

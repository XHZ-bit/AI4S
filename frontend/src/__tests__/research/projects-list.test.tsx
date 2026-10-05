import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import ResearchProjectsPage from "../../pages/research/ResearchProjectsPage";
import { project } from "./fixtures";

const api = vi.hoisted(() => ({ listProjects: vi.fn(), createProject: vi.fn() }));
vi.mock("../../api/projects", () => api);

beforeEach(() => {
  api.listProjects.mockReset().mockResolvedValue({ items: [], next_cursor: null });
  api.createProject.mockReset().mockResolvedValue(project);
});

test("empty project state is explicit", async () => {
  render(<MemoryRouter><ResearchProjectsPage /></MemoryRouter>);
  expect(await screen.findByText("还没有课题")).toBeTruthy();
});

test("StrictMode double interaction creates a project once", async () => {
  let resolveCreate: (value: typeof project) => void = () => undefined;
  api.createProject.mockImplementation(() => new Promise(resolve => { resolveCreate = resolve; }));
  render(<StrictMode><MemoryRouter initialEntries={["/research"]}><Routes><Route path="/research" element={<ResearchProjectsPage />} /><Route path="/research/:id" element={<div>opened</div>} /></Routes></MemoryRouter></StrictMode>);
  fireEvent.click(await screen.findByRole("button", { name: "建立第一个课题" }));
  fireEvent.change(screen.getByLabelText("课题名称"), { target: { value: "异常检测课题" } });
  fireEvent.change(screen.getByLabelText("研究问题"), { target: { value: "选择什么路线？" } });
  fireEvent.change(screen.getByLabelText("首轮验证目标"), { target: { value: "验证可行性" } });
  const submit = screen.getAllByRole("button", { name: "建立课题" }).find(button => button.getAttribute("type") === "submit")!;
  fireEvent.click(submit);
  fireEvent.click(submit);
  await waitFor(() => expect(api.createProject).toHaveBeenCalledTimes(1));
  resolveCreate(project);
  expect(await screen.findByText("opened")).toBeTruthy();
});

import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import ResearchProjectsPage from "../../pages/research/ResearchProjectsPage";
import { project } from "./fixtures";

const api = vi.hoisted(() => ({ listProjects: vi.fn(), createProject: vi.fn() }));
vi.mock("../../api/projects", () => api);
vi.mock("../../api/knowledge", () => ({ saveKnowledgePreferences: vi.fn(async () => ({ mode: 'explore' })) }));

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
  fireEvent.click(screen.getByText('已有想法？补充领域、问题和目标'));
  fireEvent.click(screen.getByRole('button',{name:/已有明确问题/}));
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

test('an exploratory workspace does not require a specific question or validation objective',async()=>{
  render(<MemoryRouter><ResearchProjectsPage/></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button',{name:'建立第一个课题'}));
  fireEvent.change(screen.getByLabelText('课题名称'),{target:{value:'我的跨学科探索'}});
  fireEvent.click(screen.getByText('已有想法？补充领域、问题和目标'));
  fireEvent.change(screen.getByRole('combobox',{name:'研究领域'}),{target:{value:'数字人文'}});
  fireEvent.click(screen.getByRole('button',{name:'建立探索空间'}));
  await waitFor(()=>expect(api.createProject).toHaveBeenCalledWith(expect.objectContaining({domain:'custom',custom_domain:'数字人文',stage:'exploring',research_question:'',constraints:expect.objectContaining({objective:''})})));
});


test('a workspace can be created by entering only its temporary name',async()=>{
 render(<MemoryRouter initialEntries={['/research?new=1']}><ResearchProjectsPage/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('课题名称'),{target:{value:'一个新想法'}});
 expect(screen.getByText('已有想法？补充领域、问题和目标').closest('details')?.open).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'建立探索空间'}));
 await waitFor(()=>expect(api.createProject).toHaveBeenCalledWith(expect.objectContaining({title:'一个新想法',domain:'custom',stage:'exploring',research_question:'',constraints:expect.objectContaining({objective:''})})));
});

import { fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import { apiGet, apiPost } from "../api/client";
import { listLibraryPapers, type LibraryPaper } from "../api/library";
import { collect, startExtract } from "../api/papers";
import { AccessModeProvider } from "../components/SessionContext";
import Manage from "../pages/Manage";

vi.mock("../api/client", () => ({ apiGet: vi.fn(), apiPost:vi.fn() }));
vi.mock("../api/library", () => ({ listLibraryPapers: vi.fn(), updateLibraryPaper: vi.fn() }));
vi.mock("../api/papers", () => ({ collect: vi.fn(), startExtract: vi.fn(), uploadPdf: vi.fn() }));

const button = (label: string | RegExp) => screen.getByText(label).closest("button")!;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listLibraryPapers).mockResolvedValue({ items: [{ uid: "p", title: "Private paper" } as LibraryPaper], total: 1 });
});

test("multiuser explains unavailable collection and extraction with actual configured upload limits", async () => {
  vi.mocked(apiGet).mockResolvedValue({ limits: { pdf_max_bytes: 2 * 1024 ** 2, pdf_max_pages: 12, max_papers: 7, storage_max_bytes: 15 * 1024 ** 2 } });
  render(<MemoryRouter><AccessModeProvider mode="multiuser"><Manage /></AccessModeProvider></MemoryRouter>);
  expect((await screen.findByText("Private paper"))).toBeTruthy();
  expect(button("批量抽取").disabled).toBe(true);
  expect(screen.getByText(/多人试用暂未开放模型抽取/)).toBeTruthy();
  fireEvent.click(button("添加论文"));
  expect((await screen.findByText(/每份 PDF ≤ 2 MB/)).textContent).toContain("每份 ≤ 12 页 · 最多 7 篇论文 · 个人 PDF 总量 ≤ 15 MB");
  expect(screen.queryByText(/^采\s*集$/)).toBeNull();
  expect(screen.queryByText("从 arXiv 采集")).toBeNull();
  expect(screen.queryByLabelText("关键词")).toBeNull();

  expect(button("上传 PDF").disabled).toBe(false);
  expect(collect).not.toHaveBeenCalled(); expect(startExtract).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("检索与发现"));
  expect(screen.getByText(/多人试用暂未开放联网采集/)).toBeTruthy();
  expect(apiGet).toHaveBeenCalledWith("/api/system/status", undefined, expect.any(AbortSignal));
});

test("quota load failure leaves uploading available and can be retried", async () => {
  let attempt=0;vi.mocked(apiGet).mockImplementation(async(path)=>{if(path==="/api/projects")return {items:[]};if(++attempt===1)throw new Error("Offline");return {limits:{pdf_max_bytes:1024**2,pdf_max_pages:5,max_papers:4,storage_max_bytes:8*1024**2}}});
  render(<MemoryRouter><AccessModeProvider mode="multiuser"><Manage /></AccessModeProvider></MemoryRouter>);
  fireEvent.click(button("添加论文"));
  fireEvent.click(await screen.findByText("重试读取配额"));
  expect(await screen.findByText(/每份 PDF ≤ 1 MB/)).toBeTruthy();
  expect(button("上传 PDF").disabled).toBe(false);
  expect(screen.queryByText(/无法读取上传配额/)).toBeNull();
});

test("local mode keeps collection and model extraction available without a quota request", async () => {
  render(<MemoryRouter><Manage /></MemoryRouter>);
  const row = (await screen.findByText("Private paper")).closest("tr")!;
  expect(screen.queryByText("上传 PDF")).toBeNull();
  fireEvent.click(within(row).getByRole("checkbox"));
  expect(button("批量抽取").disabled).toBe(false);
  fireEvent.click(screen.getByText("检索与发现"));
  const collection = button("从 arXiv 采集");
  expect(collection.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByLabelText("关键词")).toBeNull();
  fireEvent.click(collection);
  expect(collection.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByLabelText("关键词")).toBeTruthy();
  expect(button(/^采\s*集$/).disabled).toBe(false);
  expect(screen.queryByText(/多人试用暂未开放/)).toBeNull();
  expect(apiGet).not.toHaveBeenCalled();
});


test("legacy add link keeps the project and imports directly into its reading workspace", async()=>{
 vi.mocked(apiGet).mockImplementation(async(path)=>path==="/api/projects"?{items:[{id:"project-a",title:"My research"}]}:{project:{title:"My research"},papers:[]});
 vi.mocked(apiPost).mockResolvedValue({uid:"p",duplicate:true,notice:"Saved"});
 render(<MemoryRouter initialEntries={["/manage?project=project-a&add=1"]}><Manage/></MemoryRouter>);
 expect(await screen.findByText("My research · 添加后可在空间内继续阅读")).toBeTruthy();
 expect(screen.getByText("← 返回当前研究空间").getAttribute("href")).toBe("/research/project-a?tab=reading");
 fireEvent.change(screen.getByLabelText("论文链接或标识"),{target:{value:"2303.04137"}});
 fireEvent.click(screen.getByLabelText("添加论文标识"));
 expect(await screen.findByText("已加入研究空间")).toBeTruthy();
 expect(apiPost).toHaveBeenCalledWith("/api/workbench/import",{value:"2303.04137",project_id:"project-a"});
 expect(screen.getByText("打开论文").getAttribute("href")).toBe("/research/project-a?tab=reading&paper=p");
 fireEvent.click(screen.getByText("从资料库选择"));
 expect(await screen.findByLabelText("加入研究空间：Private paper")).toBeTruthy();
});

test("existing library paper can retry project binding and then reads inside the same workspace",async()=>{
 let linked=false;
 vi.mocked(apiGet).mockImplementation(async()=>({project:{title:"My research"},papers:linked?[{uid:"p"}]:[]}));
 vi.mocked(apiPost).mockRejectedValueOnce(new Error("Offline")).mockImplementation(async()=>{linked=true;return {linked:true}});
 render(<MemoryRouter initialEntries={["/manage?project=project-a&view=library"]}><Manage/></MemoryRouter>);
 const add=await screen.findByLabelText("加入研究空间：Private paper");
 await waitFor(()=>expect((add as HTMLButtonElement).disabled).toBe(false));
 expect(screen.getByLabelText("阅读原文：Private paper").getAttribute("href")).toBe("/papers/p?tab=reading&project=project-a");
 fireEvent.click(add);expect(await screen.findByText(/未能加入研究空间：Error: Offline/)).toBeTruthy();
 fireEvent.click(screen.getByLabelText("加入研究空间：Private paper"));
 expect(await screen.findByLabelText("已加入研究空间：Private paper")).toBeTruthy();
 expect(apiPost).toHaveBeenLastCalledWith("/api/workbench/projects/project-a/papers",{paper_uid:"p"});
 await waitFor(()=>expect(screen.getByLabelText("阅读原文：Private paper").getAttribute("href")).toBe("/research/project-a?tab=reading&paper=p"));
});


test("batch binding skips existing project papers",async()=>{
 vi.mocked(apiGet).mockResolvedValue({project:{title:"My research"},papers:[{uid:"p1"}]});
 vi.mocked(listLibraryPapers).mockResolvedValue({items:[{uid:"p1",title:"Already linked"} as LibraryPaper,{uid:"p2",title:"New reference"} as LibraryPaper],total:2});
 vi.mocked(apiPost).mockResolvedValue({linked:true});
 render(<MemoryRouter initialEntries={["/manage?project=project-a&view=library"]}><Manage/></MemoryRouter>);
 await screen.findByText("New reference");
 fireEvent.click(document.querySelector('thead input[type="checkbox"]')!);
 fireEvent.click(button("将所选加入研究空间"));
 await waitFor(()=>expect(apiPost).toHaveBeenCalledTimes(1));
 expect(apiPost).toHaveBeenCalledWith("/api/workbench/projects/project-a/papers",{paper_uid:"p2"});
 expect(await screen.findByLabelText("已加入研究空间：New reference")).toBeTruthy();
});

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";
import * as client from "../api/client";
import * as workflow from "../api/workflow";
import WorkflowHub from "../pages/WorkflowHub";
import Tasks from "../pages/Tasks";
import Actions from "../pages/Actions";
import RuntimeStatus from "../components/RuntimeStatus";
import PaperQuality from "../components/PaperQuality";

vi.mock("../api/client", () => ({ apiGet:vi.fn(), apiPost:vi.fn() }));
vi.mock("../api/workflow", () => ({ workflowOverview:vi.fn(), workflowActivities:vi.fn(), listMastery:vi.fn(), workflowRecommendations:vi.fn() }));
afterEach(() => { vi.useRealTimers(); vi.resetAllMocks(); });

test("one failed workflow section preserves successful activity and suggestions", async () => {
  vi.mocked(client.apiGet).mockResolvedValue({items:[]});
  vi.mocked(workflow.workflowOverview).mockRejectedValue(new Error("503 overview"));
  vi.mocked(workflow.workflowActivities).mockResolvedValue({items:[{id:"paper:p:read:x",source_kind:"paper",source_id:"p",source_version:"v",item_id:"read:x",title:"Read original",status:"pending",evidence_level:"none",url:"/papers/p",detail:"Original",evidence_ids:[],estimated_minutes:5,project_id:null}],total:1,offset:0,limit:50});
  vi.mocked(workflow.listMastery).mockResolvedValue({items:[]});
  vi.mocked(workflow.workflowRecommendations).mockResolvedValue({items:[],total:0,truncated:false,contract_version:"workflow-recommendations-v1",input_fingerprint:"f",ranking_rule_version:"v",notice:"Fixed rules"});
  render(<MemoryRouter><WorkflowHub/></MemoryRouter>);
  expect(await screen.findByRole("link",{name:"Read original"})).toBeTruthy();
  expect(screen.getByText(/概览加载失败/)).toBeTruthy();
  expect(screen.queryByText("暂无符合条件的活动。")).toBeNull();
});

test("task polling does not overlap slow requests and aborts on unmount", async () => {
  vi.useFakeTimers();
  let resolve!: (value:any)=>void;
  vi.mocked(client.apiGet).mockReturnValue(new Promise(value=>{resolve=value;}));
  const mounted=render(<MemoryRouter><Tasks/></MemoryRouter>);
  await act(async()=>{vi.advanceTimersByTime(15000);});
  expect(client.apiGet).toHaveBeenCalledTimes(1);
  const signal=vi.mocked(client.apiGet).mock.calls[0][2];
  await act(async()=>{resolve({items:[],total:0});});
  mounted.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async()=>{vi.advanceTimersByTime(15000);});
  expect(client.apiGet).toHaveBeenCalledTimes(1);
});

test("task failure uses backoff and keeps explicit error state", async()=>{
  vi.useFakeTimers();
  vi.mocked(client.apiGet).mockRejectedValue(new Error("offline"));
  render(<MemoryRouter><Tasks/></MemoryRouter>);
  await act(async()=>{});
  expect(screen.getByText("任务加载或操作失败")).toBeTruthy();
  await act(async()=>{vi.advanceTimersByTime(3000);});
  expect(client.apiGet).toHaveBeenCalledTimes(1);
  await act(async()=>{vi.advanceTimersByTime(3000);});
  expect(client.apiGet).toHaveBeenCalledTimes(2);
});

test("runtime and PDF coverage show their precise available scope", async()=>{
  vi.mocked(client.apiGet).mockImplementation(async(path)=>path.includes("system")?{
    mode:"local",data_dir:"isolated/data",services:{database:{status:"available"},graph:{status:"unavailable",reason:"Graph offline"},parser:{status:"fallback"},model:{status:"unconfigured"}},capabilities:{graph:false,research_model:false}
  }:{status:"partial",page_count:2,text_page_count:1,warnings:["扫描页没有文字层"],measurement:"文字层覆盖率",document_versions:2});
  render(<MemoryRouter><RuntimeStatus/><PaperQuality uid="p"/></MemoryRouter>);
  expect(await screen.findByText("Graph offline")).toBeTruthy();
  expect(await screen.findByText("有文字层 1/2 页")).toBeTruthy();
  expect(screen.getByRole("link",{name:"生成自动行动清单"}).getAttribute("href")).toBe("/actions?paper=p");
});

test("automatic actions preview saves fingerprint and remains reloadable", async()=>{
  const payload={id:"saved",title:"我的自动行动清单",version:1,versions:[1],needs_review:false,estimated_minutes:5,unscheduled_count:1,input_fingerprint:"f",items:[{id:"x",title:"Read original",url:"/papers/p?tab=reading",status:"pending",week:1,estimated_minutes:5}],notice:"Automatic evidence"};
  vi.mocked(client.apiGet).mockImplementation(async(path)=>path==="/api/papers"?{items:[{uid:"p",title:"My paper"}]}:path==="/api/roadmap/auto-targets"?{items:[]}:path==="/api/actions/v1"?{items:[],total:0}:payload);
  vi.mocked(client.apiPost).mockResolvedValue(payload);
  render(<MemoryRouter initialEntries={["/actions?paper=p"]}><Actions/></MemoryRouter>);
  // Match the visible button text directly instead of repeatedly computing
  // accessible names for the entire Ant Design form in jsdom.
  fireEvent.click((await screen.findByText("预览自动行动清单",{selector:"button > span"})).closest("button")!);
  fireEvent.click((await screen.findByText("保存自动行动清单",{selector:"button > span"})).closest("button")!);
  await waitFor(()=>expect(client.apiPost).toHaveBeenLastCalledWith("/api/actions/v1",expect.objectContaining({paper_uids:["p"],input_fingerprint:"f"}),expect.any(AbortSignal)));
  expect(await screen.findByText(/我的自动行动清单 · v1/)).toBeTruthy();
  expect(screen.getByText("Read original",{selector:"a"}).getAttribute("href")).toBe("/papers/p?tab=reading");
});

test("processing task view only loads system tasks",async()=>{
 vi.mocked(client.apiGet).mockResolvedValue({items:[],total:0});
 render(<MemoryRouter initialEntries={["/workflow?view=processing"]}><WorkflowHub/></MemoryRouter>);
 await waitFor(()=>expect(client.apiGet).toHaveBeenCalledWith("/api/system/tasks",expect.any(Object),expect.any(AbortSignal)));
 expect(workflow.workflowOverview).not.toHaveBeenCalled();expect(workflow.workflowActivities).not.toHaveBeenCalled();
 expect(screen.getByRole("combobox",{name:"任务状态筛选"})).toBeTruthy();
});

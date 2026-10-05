import { StrictMode } from "react";
import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CaseStudy from "../pages/CaseStudy";
import * as cases from "../api/cases";
import { apiGet } from "../api/client";
vi.mock("../api/cases",()=>({
  caseBase:(id:string)=>"/api/cases/"+id,
  getCase:vi.fn(),getCaseSession:vi.fn(),newCaseSession:vi.fn(),patchCaseSession:vi.fn(),answerCaseQuestion:vi.fn(),importCaseRun:vi.fn()
}));
vi.mock("../api/client",()=>({apiGet:vi.fn()}));
const info={
 id:"diffusion-policy-intro",version:"1.0.0",title:"源码专题",status:"策略评估待实测",notice:"源码检查不代表模型复现",
 commit:"abc",repository:"https://example.com",paper_url:"https://example.com/paper",paper_notice:"源码依据",
 steps:[{id:"orient",title:"了解范围",minutes:3,criterion:"理解范围",body:"阅读"},{id:"inspect",title:"本机检查",minutes:5,criterion:"导入 JSON",body:"不执行模型"},{id:"reflect",title:"解释结果",minutes:5,criterion:"完成检查",body:"范围"}],
 sources:[],mappings:[],questions:[{id:"scope",step:"reflect",question:"源码检查可以证明什么？",options:["复现成功","源码一致","论文正确"],source:0}],troubleshooting:[]
};
const saved={id:"s1",version:0,case_version:"1.0.0",stale:false,state:{current_step:"reflect",read_steps:[],profile:{goal:"学习",system:"Windows",compute:"CPU"},answers:{}},runs:[]};
function show() {
 return render(<StrictMode><MemoryRouter initialEntries={["/cases/diffusion-policy-intro"]}><Routes><Route path="/cases/:caseId" element={<CaseStudy/>}/></Routes></MemoryRouter></StrictMode>);
}
beforeEach(()=>{
 vi.clearAllMocks();localStorage.clear();
 vi.mocked(cases.getCase).mockResolvedValue(info);
 vi.mocked(apiGet).mockResolvedValue({items:[]});
 vi.mocked(cases.getCaseSession).mockResolvedValue(structuredClone(saved));
});
test("strict mode browsing never creates sessions implicitly",async()=>{
 show();await screen.findByText("源码专题");
 expect(screen.getByText("开始学习并保存进度").closest("button")).toBeTruthy();
 expect(cases.newCaseSession).not.toHaveBeenCalled();
 expect(screen.getByText("源码检查不代表模型复现")).toBeTruthy();
});
test("saved answers receive feedback and scope stays honest",async()=>{
 localStorage.setItem("atlas:case:diffusion-policy-intro","s1");
 const answer={...structuredClone(saved),version:1,state:{...saved.state,answers:{scope:{choice:0,correct:false,explanation:"源码检查未运行模型",attempts:1,review_step:"reflect"}}}};
 vi.mocked(cases.answerCaseQuestion).mockResolvedValue(answer);
 show();await screen.findByText("源码检查可以证明什么？");
 fireEvent.click(screen.getByLabelText("复现成功"));fireEvent.click(screen.getByText("检查回答").closest("button")!);
 expect(await screen.findByText("源码检查未运行模型")).toBeTruthy();
 expect(cases.answerCaseQuestion).toHaveBeenCalledWith("diffusion-policy-intro","s1",{version:0,question_id:"scope",choice:0});
 expect(screen.getByText("导出学习与检查报告").closest("a")?.getAttribute("href")).toContain("/sessions/s1/report");
});
test("oversized import never reaches the backend",async()=>{
 localStorage.setItem("atlas:case:diffusion-policy-intro","s1");
 vi.mocked(cases.getCaseSession).mockResolvedValue({...structuredClone(saved),state:{...saved.state,current_step:"inspect"}});
 show();const input=await screen.findByLabelText("导入检查结果 JSON");
 fireEvent.change(input,{target:{files:[new File(["x".repeat(1024*1024+1)],"large.json")]}});
 expect(await screen.findByText(/结果包超过 1 MiB/)).toBeTruthy();
 expect(cases.importCaseRun).not.toHaveBeenCalled();
});
test("conflict keeps the selected answer and shows recovery",async()=>{
 localStorage.setItem("atlas:case:diffusion-policy-intro","s1");
 vi.mocked(cases.answerCaseQuestion).mockRejectedValue(new Error("记录冲突，请重新加载"));
 show();await screen.findByText("源码检查可以证明什么？");
 fireEvent.click(screen.getByLabelText("源码一致"));fireEvent.click(screen.getByText("检查回答").closest("button")!);
 await waitFor(()=>expect(cases.answerCaseQuestion).toHaveBeenCalled());await screen.findByText(/记录冲突，请重新加载/);
 expect((screen.getByLabelText("源码一致") as HTMLInputElement).checked).toBe(true);
 expect(screen.getByText("重新加载记录").closest("button")).toBeTruthy();
});

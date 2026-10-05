import {vi} from "vitest";
import {render,screen,fireEvent} from "@testing-library/react";
import {MemoryRouter,Routes,Route} from "react-router-dom";
import PaperDetail from "../pages/PaperDetail";
const workspace={version:0,paper:{title:"Target",year:2024},documents:[],knowledge:[],reading_tasks:[],stages:[],checks:[],reproduction:{notice:"尚未实测",steps:["确认仓库"]},state:{reading:{},answers:{},experiments:[],questions:[],profile:{weekly_hours:10}}};
beforeEach(()=>{globalThis.fetch=vi.fn().mockImplementation(async(url:any)=>({ok:true,json:async()=>String(url).endsWith("/guide")?{guide:null}:workspace}));});
test("one paper links reading, reproduction and research without claiming verification",async()=>{
 render(<MemoryRouter initialEntries={["/papers/p1"]}><Routes><Route path="/papers/:uid" element={<PaperDetail/>}/></Routes></MemoryRouter>);
 await screen.findByText("Target");
 expect(screen.getByText("摘要级资料")).toBeTruthy();
 fireEvent.click(screen.getByRole("tab",{name:"基础复现"}));
 expect(await screen.findByText("尚未实测")).toBeTruthy();
 fireEvent.click(screen.getByRole("tab",{name:"研究方向"}));
 expect(await screen.findByText("待验证研究问题，不等于创新性结论")).toBeTruthy();
});

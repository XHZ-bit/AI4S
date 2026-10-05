import {vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import Roadmap from "../pages/Roadmap";
const result={id:1,version:3,goal:"test",phases:[{phase:7,title:"已核验基础",weeks:"一周",items:[{task_id:"stable",kind:"paper",uid:"p1",title:"目标论文",reason:"source",evidence:"quote",done:false}]}],innovations:[]};
beforeEach(()=>{globalThis.fetch=vi.fn().mockImplementation(async(url:any,opts:any)=>{
 if(opts?.method==="PATCH")return {ok:true,json:async()=>({...result,version:4,phases:[{...result.phases[0],items:[{...result.phases[0].items[0],done:true}]}]})};
 return {ok:true,json:async()=>String(url).includes("/roadmap/1")?result:{items:[]}};
});});
test("saved roadmap reloads and progress uses stable id and version",async()=>{
 render(<MemoryRouter initialEntries={["/roadmap?id=1"]}><Roadmap/></MemoryRouter>);
 expect(await screen.findByText("目标论文")).toBeTruthy();
 fireEvent.click(screen.getByRole("checkbox"));
 await waitFor(()=>expect(globalThis.fetch).toHaveBeenCalledWith("/api/roadmap/1/progress",expect.objectContaining({method:"PATCH",body:expect.stringContaining('"task_id":"stable"')})));
 const call=(globalThis.fetch as any).mock.calls.find((c:any)=>c[1]?.method==="PATCH");
 expect(JSON.parse(call[1].body).version).toBe(3);
});
test("generation requires explicit target selection",async()=>{
 render(<MemoryRouter><Roadmap/></MemoryRouter>);
 fireEvent.change(screen.getByPlaceholderText(/入门具身智能/),{target:{value:"target"}});
 fireEvent.click(screen.getByRole("button",{name:/生成路线/}));
 await waitFor(()=>expect(document.querySelector('[aria-invalid="true"]')).toBeTruthy(),{timeout:4000});
 expect((globalThis.fetch as any).mock.calls.some((c:any)=>c[1]?.method==="POST")).toBe(false);
});

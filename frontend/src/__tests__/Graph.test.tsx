import {vi} from "vitest";
import {StrictMode} from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
vi.mock("react-force-graph-2d",async()=>{const {forwardRef}=await import("react");return {default:forwardRef((_props:any,_ref)=><div data-testid="canvas"/>)}});
import Graph from "../pages/Graph";
beforeEach(()=>{globalThis.fetch=vi.fn().mockImplementation(async(url:any)=>({ok:true,json:async()=>String(url).includes("/nodes")?{items:[]}:{nodes:[],links:[]}}));});
test("empty graph search finishes in StrictMode",async()=>{
 render(<StrictMode><MemoryRouter><Graph/></MemoryRouter></StrictMode>);
 await screen.findByText("暂无可显示的图谱数据");
 const input=screen.getByLabelText("搜索图谱");
 fireEvent.change(input,{target:{value:"missing"}});
 fireEvent.keyDown(input,{key:"Enter",code:"Enter",charCode:13,keyCode:13});
 await screen.findByText("没有找到匹配节点，请修改关键词或清除筛选");
 await waitFor(()=>expect(document.querySelector(".ant-spin-spinning")).toBeNull());
});
test('an empty search retains the explicit project scope instead of loading the account overview',async()=>{
 render(<MemoryRouter initialEntries={['/graph?project_id=project-a']}><Graph/></MemoryRouter>);
 await screen.findByText('暂无可显示的图谱数据');
 const calls=vi.mocked(globalThis.fetch).mock.calls.map(([url])=>String(url));
 expect(calls.some(url=>url.includes('/api/knowledge/graph?')&&url.includes('overview=true')&&url.includes('project_id=project-a'))).toBe(true);
 expect(calls.some(url=>url.includes('/api/graph/overview'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:/重\s*置/}));
 await waitFor(()=>expect(vi.mocked(globalThis.fetch).mock.calls.filter(([url])=>String(url).includes('overview=true')&&String(url).includes('project_id=project-a')).length).toBeGreaterThan(1));
 expect(vi.mocked(globalThis.fetch).mock.calls.some(([url])=>String(url).includes('/api/graph/overview'))).toBe(false);
});

import {vi} from "vitest";
import {StrictMode} from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
vi.mock("react-force-graph-2d",()=>({default:()=> <div data-testid="canvas"/>}));
import Graph from "../pages/Graph";
beforeEach(()=>{globalThis.fetch=vi.fn().mockImplementation(async(url:any)=>({ok:true,json:async()=>String(url).includes("/nodes")?{items:[]}:{nodes:[],links:[]}}));});
test("empty graph search finishes in StrictMode",async()=>{
 render(<StrictMode><MemoryRouter><Graph/></MemoryRouter></StrictMode>);
 await screen.findByText("暂无可显示的图谱数据");
 const input=screen.getByPlaceholderText("搜索概念/方法/数据集...");
 fireEvent.change(input,{target:{value:"missing"}});
 fireEvent.keyDown(input,{key:"Enter",code:"Enter",charCode:13,keyCode:13});
 await screen.findByText("没有找到匹配节点，请修改关键词或清除筛选");
 await waitFor(()=>expect(document.querySelector(".ant-spin-spinning")).toBeNull());
});

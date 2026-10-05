import {vi} from "vitest";
import {render,screen} from "@testing-library/react";
import App from "../App";
beforeEach(()=>{globalThis.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[],total:0})});window.history.replaceState({},"","/");});
test("home offers three research stages without novice review navigation",async()=>{
 render(<App/>);
 expect(await screen.findByText("从读懂一篇论文，到迈出研究的下一步")).toBeTruthy();
 expect(screen.getByText("01 读懂论文")).toBeTruthy();
 expect(screen.getByText("02 基础复现")).toBeTruthy();
 expect(screen.getByText("03 研究方向")).toBeTruthy();
 expect(screen.queryByRole("link",{name:"审核"})).not.toBeTruthy();
});

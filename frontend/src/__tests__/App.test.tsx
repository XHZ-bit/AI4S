import {vi} from "vitest";
import {render,screen} from "@testing-library/react";
import App from "../App";
beforeEach(()=>{globalThis.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[],total:0})});window.history.replaceState({},"","/");});
test("home offers three research stages without novice review navigation",async()=>{
 render(<App/>);
 expect(await screen.findByText("看得见，也走得通。")).toBeTruthy();
 expect(screen.getByText("在图文之间，读懂方法")).toBeTruthy();
 expect(screen.getByText("在动手操作中，理解源码")).toBeTruthy();
 expect(screen.getByText("在条件变化中，找到路线")).toBeTruthy();
 expect(screen.queryByRole("link",{name:"审核"})).not.toBeTruthy();
});

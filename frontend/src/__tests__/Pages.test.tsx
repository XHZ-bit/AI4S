import {vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import Manage from "../pages/Manage";
import {uploadPdf} from "../api/papers";
beforeEach(()=>{globalThis.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({total:45,items:[{uid:"p1",title:"First paper",year:2024,source:"upload"}]})});});
test("paper list uses server pagination",async()=>{
 render(<MemoryRouter><Manage/></MemoryRouter>);
 expect(await screen.findByText("First paper")).toBeTruthy();
 fireEvent.click(screen.getByTitle("2"));
 await waitFor(()=>expect((globalThis.fetch as any).mock.calls.some((c:any)=>String(c[0]).includes("offset=20"))).toBe(true));
});
test("upload preserves server error detail",async()=>{
 globalThis.fetch=vi.fn().mockResolvedValue({ok:false,status:413,statusText:"Payload Too Large",json:async()=>({detail:"文件超过限制"})});
 await expect(uploadPdf(new File(["bad"],"x.pdf"))).rejects.toThrow("文件超过限制");
});

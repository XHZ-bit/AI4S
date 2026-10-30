import {vi} from "vitest";
import {act,render,screen,within} from "@testing-library/react";
import App from "../App";
import {defaultPreferences} from "../api/preferences";
// Resolve the actual lazy route before timing UI assertions. Vite's cold module
// transformation is test setup, while App still mounts the real router and page.
beforeAll(async()=>{await import('../pages/Home');});
beforeEach(()=>{
 localStorage.clear();
 globalThis.fetch=vi.fn().mockImplementation(async(input:RequestInfo|URL)=>{
  const path=new URL(String(input),window.location.origin).pathname;
  const responses:Record<string,unknown>={
   "/api/auth/session":{mode:"local",user:null},
   "/api/preferences":defaultPreferences,
   "/api/projects":{items:[],next_cursor:null},
   "/api/papers":{items:[],total:0},
   "/api/library/papers":{items:[],total:0},
   "/api/workflow/v1/overview":{counts:{pending:0,in_progress:0,completed:0,needs_review:0},next:[],snapshot_required:0,total:0},
   "/api/system/status":{mode:"local",data_dir:"test/data",services:{database:{status:"available"},graph:{status:"unavailable"},parser:{status:"fallback"},model:{status:"unconfigured"}},capabilities:{graph:false,research_model:false}},
  };
  if(!(path in responses))throw new Error(`Unexpected request in home test: ${path}`);
  return {ok:true,json:async()=>responses[path]};
 });
 window.history.replaceState({},"","/");
});
test("home starts with research spaces and two clear entry paths while retaining diagnostics and tasks",async()=>{
 // Flush the resolved session/preferences and lazy-route promises as one startup.
 await act(async()=>{render(<App/>);});
 expect(await screen.findByRole('heading',{name:'研究工作台'})).toBeTruthy();
 expect(await screen.findByRole('link',{name:/从论文开始/})).toHaveAttribute('href','/manage?add=1');
 expect(screen.getByRole('link',{name:'探索一个想法'})).toHaveAttribute('href','/research?new=1');
 const main=within(screen.getByRole('navigation',{name:'主导航'}));
 expect(main.getByRole('link',{name:'资料库'})).toHaveAttribute('href','/manage');
 expect(screen.getByRole('heading',{name:'最近研究空间'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'快速查找与跳转'})).toBeTruthy();
 expect(screen.queryByRole('searchbox',{name:'搜索论文'})).toBeNull();
 expect(screen.queryByRole('navigation',{name:'常用入口'})).toBeNull();
 expect(screen.queryByRole('link',{name:'审核'})).toBeNull();
 expect(await screen.findByText('本地数据库：可用')).toBeTruthy();
 expect(await screen.findByText(/当前研究没有待办任务/)).toBeTruthy();
 expect(screen.getAllByRole('link',{name:'任务面板'}).every(link=>link.getAttribute('href')==='/workflow')).toBe(true);
});

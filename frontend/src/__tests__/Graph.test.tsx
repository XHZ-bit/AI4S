import {vi} from "vitest";
import {StrictMode} from "react";
import {act,render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
const graphCanvas=vi.hoisted(()=>({props:undefined as any,fit:vi.fn()}));
vi.mock("react-force-graph-2d",async()=>{
 const {forwardRef,useImperativeHandle}=await import("react");
 return {default:forwardRef((props:any,ref)=>{
  graphCanvas.props=props;
  useImperativeHandle(ref,()=>({zoomToFit:graphCanvas.fit,d3Force:()=>({strength(){},distance(){}}),d3ReheatSimulation(){},refresh(){}}),[]);
  return <div data-testid="canvas" data-width={props.width} data-height={props.height}/>;
 })};
});
import Graph from "../pages/Graph";
beforeEach(()=>{graphCanvas.fit.mockClear();globalThis.fetch=vi.fn().mockImplementation(async(url:any)=>({ok:true,json:async()=>String(url).includes("/nodes")?{items:[]}:{nodes:[],links:[]}}));});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
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

function populatedGraph(){
 vi.mocked(globalThis.fetch).mockImplementation(async()=>({ok:true,json:async()=>({nodes:[{id:'concept-1',label:'链式法则',kind:'concept'}],edges:[],scopes:[]})}) as Response);
}

test('selection and double clicks keep the user camera; fitting requires the explicit action',async()=>{
 populatedGraph();
 render(<MemoryRouter><Graph/></MemoryRouter>);
 await screen.findByText('1 节点 · 0 关系');
 const originalData=graphCanvas.props.graphData;
 expect(graphCanvas.props.enableZoomInteraction).toBe(true);
 act(()=>graphCanvas.props.onEngineStop?.());
 act(()=>graphCanvas.props.onNodeClick(originalData.nodes[0]));
 expect(await screen.findByText('节点详情')).toBeVisible();
 expect(graphCanvas.props.graphData).toBe(originalData);
 fireEvent.click(screen.getByRole('button',{name:'关闭节点详情'}));
 fireEvent.change(screen.getByLabelText('搜索图谱'),{target:{value:'链式'}});
 fireEvent.click(screen.getByRole('button',{name:'显示对象列表'}));
 fireEvent.doubleClick(screen.getByTestId('canvas'));
 act(()=>graphCanvas.props.onEngineStop?.());
 expect(graphCanvas.props.graphData).toBe(originalData);
 expect(graphCanvas.fit).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'适配画布'}));
 expect(graphCanvas.fit).toHaveBeenCalledExactlyOnceWith(400);
});

test('global graph selected nodes brighten their fill without drawing a selection ring',async()=>{
 populatedGraph();render(<MemoryRouter><Graph/></MemoryRouter>);
 await screen.findByText('1 节点 · 0 关系');
 const node={...graphCanvas.props.graphData.nodes[0],x:10,y:20};
 act(()=>graphCanvas.props.onNodeClick(node));
 const ctx={save:vi.fn(),restore:vi.fn(),beginPath:vi.fn(),arc:vi.fn(),fill:vi.fn(),stroke:vi.fn(),measureText:()=>({width:12}),fillText:vi.fn(),fillStyle:'',shadowBlur:0} as any;
 graphCanvas.props.nodeCanvasObject(node,ctx,1);
 expect(ctx.stroke).not.toHaveBeenCalled();expect(ctx.arc).toHaveBeenCalledTimes(1);
 expect(ctx.arc.mock.calls[0][2]).toBeGreaterThan(4);expect(ctx.fill).toHaveBeenCalledOnce();
 expect(ctx.fillText).toHaveBeenCalledWith('链式法则',10,27);
});

test('canvas follows the available viewport and reclaims directory width without fixed pixel sizing',async()=>{
 populatedGraph();
 let top=200;
 const callbacks=new Set<ResizeObserverCallback>();
 vi.stubGlobal('ResizeObserver',class {
  callback:ResizeObserverCallback;
  constructor(callback:ResizeObserverCallback){this.callback=callback;callbacks.add(callback)}
  observe(){} unobserve(){} disconnect(){callbacks.delete(this.callback)}
 });
 vi.spyOn(window,'innerHeight','get').mockReturnValue(900);
 const nativeBounds=HTMLElement.prototype.getBoundingClientRect;
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  if(this.classList.contains('atlas-graph-workspace'))return {top,width:1000,height:0,bottom:top,left:0,right:1000,x:0,y:top,toJSON(){}};
  if(this.classList.contains('atlas-graph-stage')){
   const directory=this.parentElement?.querySelector<HTMLElement>('.graph-object-list');
   const width=directory&&!directory.hidden?778:1000;
   return {top,width,height:0,bottom:top,left:0,right:width,x:0,y:top,toJSON(){}};
  }
  return nativeBounds.call(this);
 });
 render(<MemoryRouter><Graph/></MemoryRouter>);
 const canvas=await screen.findByTestId('canvas');
 await screen.findByText('1 节点 · 0 关系');
 expect(canvas).toHaveAttribute('data-height','684');
 expect(canvas).toHaveAttribute('data-width','1000');
 fireEvent.click(screen.getByRole('button',{name:'显示对象列表'}));
 expect(canvas).toHaveAttribute('data-width','778');
 fireEvent.click(screen.getByRole('button',{name:'收起对象列表'}));
 expect(canvas).toHaveAttribute('data-width','1000');
 top=260;
 act(()=>callbacks.forEach(callback=>callback([],{} as ResizeObserver)));
 await waitFor(()=>expect(canvas).toHaveAttribute('data-height','624'));
 vi.spyOn(window,'innerHeight','get').mockReturnValue(760);
 fireEvent(window,new Event('resize'));
 await waitFor(()=>expect(canvas).toHaveAttribute('data-height','484'));
});

test('collapsed directory retains keyboard accessible equivalent navigation in list view',async()=>{
 populatedGraph();
 render(<MemoryRouter><Graph/></MemoryRouter>);
 await screen.findByText('1 节点 · 0 关系');
 expect(screen.queryByRole('complementary',{name:'图谱对象列表'})).toBeNull();
 fireEvent.click(screen.getByRole('radio',{name:'列表'}));
 expect(screen.getByRole('complementary',{name:'图谱对象列表'})).toBeVisible();
 const node=screen.getByRole('button',{name:'链式法则 · 概念'});
 fireEvent.click(node);
 expect(await screen.findByText('节点详情')).toBeVisible();
 expect(screen.getByRole('button',{name:'继续展开相关节点'})).toBeVisible();
});

test('graph draft restores while options stay closed and provenance opens without an extra layout row',async()=>{
 localStorage.clear();
 const draft={data:{nodes:[{uid:'saved-node',name:'已保存概念',type:'concept'}],links:[]},history:[],query:''};
 vi.mocked(globalThis.fetch).mockImplementation(async(url:any)=>({ok:true,json:async()=>String(url).includes('/api/workbench/records/')?{body:JSON.stringify(draft),version:1}:{nodes:[],links:[]}}) as Response);
 render(<MemoryRouter><Graph seed="paper-1"/></MemoryRouter>);
 await screen.findByText('1 节点 · 0 关系');
 const options=screen.getByText('图谱选项').closest('details')!;
 expect(options).not.toHaveAttribute('open');
 const syncStatus=options.querySelector('.graph-sync-details [role="status"]')!;
 expect(syncStatus).not.toBeVisible();
 expect(vi.mocked(globalThis.fetch).mock.calls.some(([url])=>String(url).includes('/api/workbench/records/'))).toBe(true);
 fireEvent.click(screen.getByText('图谱选项'));
 expect(options).toHaveAttribute('open');
 expect(syncStatus).toBeVisible();
 fireEvent.keyDown(options,{key:'Escape'});
 expect(options).not.toHaveAttribute('open');
});

test('canvas avoids the phone navigation and resizes when the on-screen keyboard reduces the viewport',async()=>{
 populatedGraph();
 const viewport=Object.assign(new EventTarget(),{height:860,offsetTop:0});
 vi.stubGlobal('visualViewport',viewport);
 const nativeBounds=HTMLElement.prototype.getBoundingClientRect;
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  if(this.classList.contains('atlas-mobile-navigation'))return {top:780,width:390,height:64,bottom:844,left:0,right:390,x:0,y:780,toJSON(){}};
  if(this.classList.contains('graph-options'))return {top:140,width:100,height:40,bottom:180,left:258,right:358,x:258,y:140,toJSON(){}};
  if(this.classList.contains('atlas-graph-workspace')||this.classList.contains('atlas-graph-stage'))return {top:180,width:358,height:0,bottom:180,left:0,right:358,x:0,y:180,toJSON(){}};
  return nativeBounds.call(this);
 });
 render(<MemoryRouter><Graph/><nav className="atlas-mobile-navigation"/></MemoryRouter>);
 const canvas=await screen.findByTestId('canvas');
 expect(canvas).toHaveAttribute('data-height','584');
 const explorer=canvas.closest<HTMLElement>('.atlas-graph-explorer')!;
 const initialOptionsHeight=parseFloat(explorer.style.getPropertyValue('--graph-options-height'));
 expect(initialOptionsHeight+180+8).toBeLessThanOrEqual(780);
 viewport.height=520;
 act(()=>viewport.dispatchEvent(new Event('resize')));
 await waitFor(()=>expect(canvas).toHaveAttribute('data-height','324'));
 expect(canvas).toHaveAttribute('data-width','358');
 const keyboardOptionsHeight=parseFloat(explorer.style.getPropertyValue('--graph-options-height'));
 expect(keyboardOptionsHeight).toBeLessThan(initialOptionsHeight);
 expect(keyboardOptionsHeight+180+8).toBeLessThanOrEqual(viewport.height);
});

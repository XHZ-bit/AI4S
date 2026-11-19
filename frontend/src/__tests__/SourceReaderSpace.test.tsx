import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {SourceReader} from '../components/knowledge/KnowledgeSources';
import type {KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({source:vi.fn(),node:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),getKnowledgeSource:api.source,getKnowledgeNode:api.node}));
vi.mock('../components/workspace/PdfReader',()=>({default:({initialPage,targetPage}:{initialPage:number;targetPage?:number})=><div aria-label="测试PDF宿主"><output>{initialPage} / {targetPage}</output></div>}));
vi.mock('../components/workbench/ProjectWorkbench',()=>({default:()=>null}));
vi.mock('../components/knowledge/FormulaContext',()=>({default:()=> <section aria-label="公式说明内容">已保存的符号说明</section>}));
let documentTop=220,observers:(()=>void)[]=[];
const originalScrollIntoView=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'scrollIntoView');
const block=(id='b',kind='text')=>({id,ordinal:0,kind,heading:'正文 '+id,text:'This is the original source text.',page:null,metadata:{}});
const source=(overrides:Record<string,unknown>={}):KnowledgeSource=>({id:'s',project_id:'p',asset_id:'asset',version:'v1',title:'Original document',filename:'source.md',kind:'report',media_type:'text/markdown',created_at:'2026-11-17',removed:false,blocks:[block()],knowledge_nodes:[],...overrides} as KnowledgeSource);
beforeEach(()=>{
 vi.clearAllMocks();documentTop=220;observers=[];
 Object.defineProperty(window,'innerHeight',{configurable:true,value:768});
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  const line=this.id.startsWith('kw-line-');const top=line?500:documentTop,height=line?24:400;
  return{top,height,width:900,bottom:top+height,left:0,right:900,x:0,y:top,toJSON:()=>({})};
 });
 vi.stubGlobal('ResizeObserver',class{constructor(callback:()=>void){observers.push(callback)}observe(){}disconnect(){}});
 api.source.mockResolvedValue(source());api.node.mockResolvedValue({node:{metadata:{}},evidence:[]});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();if(originalScrollIntoView)Object.defineProperty(HTMLElement.prototype,'scrollIntoView',originalScrollIntoView);else Reflect.deleteProperty(HTMLElement.prototype,'scrollIntoView')});

test('source, formula and related actions share a compact bar without remounting the PDF',async()=>{
 api.source.mockResolvedValue(source({kind:'paper',filename:'paper.pdf',media_type:'application/pdf',blocks:[{...block(),page:4}],knowledge_nodes:[{id:'formula',kind:'formula',label:'缩放公式',block_ids:['b']}]}));
 const learn=vi.fn();render(<SourceReader projectId="p" sourceId="s" sourcePicker={<select aria-label="当前资料"><option>Attention</option></select>} page={4} targetPage={4} blockId="b" onLearn={learn}/>);
 const pdf=await screen.findByLabelText('测试PDF宿主'),bar=document.querySelector('.kw-source-command-bar')!;
 expect(bar.contains(screen.getByLabelText('当前资料'))).toBe(true);expect(bar.contains(screen.getByRole('link',{name:'下载原文件'}))).toBe(true);expect(bar.contains(screen.getByRole('button',{name:'学习这条公式'}))).toBe(true);
 expect(api.node).not.toHaveBeenCalled();fireEvent.click(screen.getByText('查看公式符号与条件',{selector:'summary'}));await screen.findByText('已保存的符号说明');
 fireEvent.click(screen.getByText('第 4 页关联知识 · 1',{selector:'summary'}));fireEvent.click(await screen.findByRole('button',{name:'深入学习此处'}));
 expect(learn).toHaveBeenCalledWith('formula',{block:'b',page:4});expect(screen.getByLabelText('测试PDF宿主')).toBe(pdf);expect(pdf).toHaveTextContent('4 / 4');expect(api.source).toHaveBeenCalledTimes(1);
});

test('text content fills actual viewport space and keeps find inside its chapter pane',async()=>{
 render(<SourceReader projectId="p" sourceId="s"/>);
 const body=await screen.findByRole('article',{name:'原文内容'}),layout=body.closest('.kw-document-layout')!;
 expect(layout).toHaveStyle({'--kw-document-height':'536px'});
 expect(within(screen.getByRole('navigation',{name:'资料章节'})).getByLabelText('在当前资料中查找')).toBeVisible();
 body.scrollTop=160;documentTop=140;Object.defineProperty(window,'innerHeight',{configurable:true,value:900});act(()=>window.dispatchEvent(new Event('resize')));
 expect(layout).toHaveStyle({'--kw-document-height':'748px'});expect(screen.getByRole('article',{name:'原文内容'})).toBe(body);expect(body.scrollTop).toBe(160);
 fireEvent.change(screen.getByLabelText('在当前资料中查找'),{target:{value:'not present'}});expect(await screen.findByText('没有匹配内容。')).toBeVisible();
});

test('an exact code line is highlighted and located inside the document rather than scrolling the page',async()=>{
 api.source.mockResolvedValue(source({kind:'code',filename:'model.repo.json',media_type:'application/json',blocks:[{...block('code','code'),heading:'Model.forward',text:'first\nsecond\nthird',metadata:{path:'model.py',start_line:10,end_line:12}}]}));
 const scrollIntoView=vi.fn();Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,writable:true,value:scrollIntoView});
 vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockImplementation(function(this:HTMLElement){return this.classList.contains('kw-document')?400:0});
 render(<SourceReader projectId="p" sourceId="s" blockId="code" startLine={11} endLine={12}/>);
 const body=await screen.findByRole('article',{name:'源码阅读区'});Object.defineProperty(body,'clientHeight',{configurable:true,value:400});
 await waitFor(()=>expect(body.scrollTop).toBe(92));
 expect(document.getElementById('kw-line-code-11')).toHaveClass('kw-code-line-highlight');expect(document.getElementById('kw-line-code-12')).toHaveClass('kw-code-line-highlight');expect(scrollIntoView).not.toHaveBeenCalled();
 expect(screen.getByRole('link',{name:'下载仓库快照'})).toBeVisible();
});

test('chapter links keep the document mounted and do not use browser hash scrolling',async()=>{
 api.source.mockResolvedValue(source({blocks:[block('first'),block('second')]}));render(<SourceReader projectId="p" sourceId="s"/>);
 const body=await screen.findByRole('article',{name:'原文内容'});Object.defineProperty(body,'clientHeight',{configurable:true,value:400});
 const anchor=within(screen.getByRole('navigation',{name:'资料章节'})).getByRole('link',{name:'正文 second'}),click=new MouseEvent('click',{bubbles:true,cancelable:true});fireEvent(anchor,click);
 expect(click.defaultPrevented).toBe(true);expect(document.getElementById('kw-block-second')).toHaveClass('kw-active-source-block');expect(screen.getByRole('article',{name:'原文内容'})).toBe(body);
});

test('a late document response cannot replace a newly selected source',async()=>{
 let finish!:(value:KnowledgeSource)=>void;api.source.mockImplementation((_p:string,id:string)=>id==='old'?new Promise<KnowledgeSource>(resolve=>{finish=resolve}):Promise.resolve(source({id:'new',title:'New document'})));
 const ui=render(<SourceReader projectId="p" sourceId="old"/>);ui.rerender(<SourceReader projectId="p" sourceId="new"/>);await screen.findByRole('heading',{name:'New document'});
 await act(async()=>{finish(source({id:'old',title:'Old document'}))});expect(screen.queryByRole('heading',{name:'Old document'})).toBeNull();expect(screen.getByRole('heading',{name:'New document'})).toBeVisible();
});

import {useState} from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeComparison from '../components/knowledge/KnowledgeComparison';
import type {KnowledgeComparison as Comparison,KnowledgeNode,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({list:vi.fn(),preview:vi.fn(),revise:vi.fn(),compare:vi.fn(),graph:vi.fn(),node:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),listKnowledgeComparisons:api.list,previewKnowledgeComparison:api.preview,reviseKnowledgeComparison:api.revise,compareKnowledgeSources:api.compare,getKnowledgeGraph:api.graph,getKnowledgeNode:api.node}));
vi.mock('../api/knowledgeComparison',async()=>({...await vi.importActual<typeof import('../api/knowledgeComparison')>('../api/knowledgeComparison'),reviseComparisonCell:api.revise,listComparisonEvidence:vi.fn(async()=>({items:[]}))}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({sourceKindLabels:{paper:'论文',report:'研究报告'},EvidenceList:()=>null}));
vi.mock('../components/learning/MathText',()=>({default:({text}:{text:string})=><span>{text}</span>}));

const sources:KnowledgeSource[]=[{id:'s1',project_id:'p1',asset_id:'a1',version:'v1',title:'相关论文',filename:'paper.pdf',kind:'paper',media_type:'application/pdf',removed:false,created_at:'then'},{id:'s2',project_id:'p1',asset_id:'a2',version:'v2',title:'我的方法',filename:'report.docx',kind:'report',media_type:'application/docx',removed:false,created_at:'then'}];
const method=(id:string):KnowledgeNode=>({id,project_id:'p1',source_id:'s2',kind:'method',label:id==='context-method'?'D2当前聚焦':'旧整体方法',summary:'Actual method',parent_id:null,origin:'source',research_status:'implemented',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{}});
function comparison(dimensions=['信息路径与机制'],text='自动整理的机制',changes:Partial<Comparison>={}):Comparison{
 return {id:'comparison-1',source_ids:['s1','s2'],title:'自动比较表',revision:1,dimensions,auto_filled:true,focus_node_ids:[],focus_nodes:[],rows:dimensions.map(d=>({dimension:d,compatibility:'根据已有知识',values:sources.map(s=>({source_id:s.id,text:s.id==='s1'?text:'另一份资料的依据',node_ids:[],evidence_ids:[],origin:'source'}))})),evidence:[],status:'basic',cached:false,stale:false,usage:{},errors:[],...changes};
}
function Show({initialId,contextNodeId}:{initialId?:string;contextNodeId?:string}){
 const [id,setId]=useState(initialId);
 return <KnowledgeComparison projectId="p1" sources={sources} comparisonId={id} contextNodeId={contextNodeId} onComparison={setId} onNode={vi.fn()} onEvidence={vi.fn()}/>;
}
beforeEach(()=>{
 Object.values(api).forEach(fn=>fn.mockReset());
 api.list.mockResolvedValue({items:[]});
 api.graph.mockResolvedValue({nodes:[method('old-method'),method('context-method')],edges:[],total_nodes:2,total_edges:0,truncated:false});
 api.node.mockResolvedValue({node:method('context-method'),edges:[],neighbors:[],evidence:[],prerequisites:[],resources:[],demos:[]});
 api.preview.mockImplementation(async(_p:string,_sources:string[],_focus:string[],dimensions:string[])=>comparison(dimensions));
});

test('opening comparison restores cached results and automatically requests GET preview without a model POST',async()=>{
 const cached=comparison(['协调机制'],'已保存的用户比较',{status:'ready',cached:true,revision:4});
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 render(<Show/>);
 await screen.findByText('已保存的用户比较');
 await waitFor(()=>expect(api.preview).toHaveBeenCalledWith('p1',['s1','s2'],[],['协调机制'],expect.any(AbortSignal)));
 expect(screen.getByText('复用已保存结果')).toBeTruthy();
 expect(api.compare).not.toHaveBeenCalled();expect(api.revise).not.toHaveBeenCalled();
});

test('typing a custom comparison dimension automatically displays its new table row without generation',async()=>{
 render(<Show/>);await screen.findAllByText('自动整理的机制');
 fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));
 const tags=screen.getByRole('combobox',{name:'比较关注点'});
 fireEvent.change(tags,{target:{value:'通信延迟'}});fireEvent.keyDown(tags,{key:'Enter',code:'Enter',keyCode:13,which:13});
 await screen.findByText('通信延迟',{selector:'strong'});
 expect(api.preview.mock.lastCall?.[3]).toContain('通信延迟');
 expect(api.compare).not.toHaveBeenCalled();
});

test('a per-cell PATCH displays its returned revision and persists after an explicit GET reopen',async()=>{
 let server=comparison();
 api.preview.mockImplementation(async()=>server);
 api.revise.mockImplementation(async()=>{server=comparison(['信息路径与机制'],'用户确认的跨分支信息路径',{revision:2,status:'ready',cached:true});server.rows[0].values[0].origin='user';return server});
 const first=render(<Show/>);await screen.findByText('自动整理的机制');
 fireEvent.click(screen.getAllByRole('button',{name:'修改或补充'})[0]);
 fireEvent.change(screen.getByRole('textbox',{name:'比较内容'}),{target:{value:'用户确认的跨分支信息路径'}});
 fireEvent.click(screen.getByRole('button',{name:'保存修订'}));
 await waitFor(()=>expect(api.revise).toHaveBeenCalledWith('p1','comparison-1',expect.objectContaining({expected_revision:1,dimension:'信息路径与机制',source_id:'s1',text:'用户确认的跨分支信息路径'})));
 await screen.findByText('用户确认的跨分支信息路径');
 expect(screen.queryByRole('textbox',{name:'比较内容'})).toBeNull();
 expect(screen.queryByText('自动整理的机制')).toBeNull();
 expect(server.revision).toBe(2);
 expect(server.rows[0].values[0].origin).toBe('user');
 first.unmount();
 api.list.mockResolvedValue({items:[server]});api.preview.mockClear();
 render(<Show initialId={server.id}/>);
 await screen.findByText('用户确认的跨分支信息路径');
 await waitFor(()=>expect(api.preview).toHaveBeenCalledWith('p1',['s1','s2'],[],['信息路径与机制'],expect.any(AbortSignal)));
 expect(screen.queryByText('自动整理的机制')).toBeNull();
 expect(screen.getByText('用户补充')).toBeVisible();
 expect(api.compare).not.toHaveBeenCalled();
});

test('legacy uncited source cells show pending evidence while cited origins and personal edits keep their labels',async()=>{
 const cached=comparison(['机制','范围'],'没有保存依据的旧内容',{status:'ready',cached:true});
 cached.rows[0].values[1]={...cached.rows[0].values[1],text:'个人补充仍保留',origin:'user'};
 cached.rows[1].values[0]={...cached.rows[1].values[0],text:'有引用的原文陈述',evidence_ids:['e1'],origin:'source'};
 cached.rows[1].values[1]={...cached.rows[1].values[1],text:'有引用的平台归纳',evidence_ids:['e2'],origin:'inference'};
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 render(<Show initialId={cached.id}/>);
 const missing=(await screen.findByText('没有保存依据的旧内容')).closest('td')!;
 expect(missing).toHaveTextContent('待补依据');expect(missing).not.toHaveTextContent('原文明示');
 expect(screen.getByText('个人补充仍保留').closest('td')).toHaveTextContent('用户补充');
 expect(screen.getByText('有引用的原文陈述').closest('td')).toHaveTextContent('原文明示');
 expect(screen.getByText('有引用的平台归纳').closest('td')).toHaveTextContent('平台归纳');
 expect(api.compare).not.toHaveBeenCalled();expect(api.revise).not.toHaveBeenCalled();
});

test('an items refresh for the same comparison ID cannot overwrite a context-selected D2 method',async()=>{
 const saved=comparison(['协调机制'],'历史比较',{status:'ready',cached:true,focus_node_ids:['old-method'],focus_nodes:[{id:'old-method',source_id:'s2',label:'旧整体方法'}]});
 api.list.mockResolvedValue({items:[saved]});
 api.preview.mockImplementation(async(_p:string,_sources:string[],focus:string[],dimensions:string[])=>comparison(dimensions,focus.includes('context-method')?'当前D2对照':'历史比较',{...saved,rows:comparison(dimensions,focus.includes('context-method')?'当前D2对照':'历史比较').rows}));
 render(<Show initialId="comparison-1" contextNodeId="context-method"/>);
 await screen.findByText('当前D2对照');
 fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));
 await act(async()=>{await Promise.resolve()});
 await waitFor(()=>expect((screen.getByRole('combobox',{name:'聚焦方法：我的方法'}) as HTMLSelectElement).value).toBe('context-method'));
 expect(api.preview.mock.lastCall?.[2]).toEqual(['context-method']);
 expect(api.compare).not.toHaveBeenCalled();
});

test('saved comparisons keep setup and relations secondary while the result table stays accessible',async()=>{
 const cached=comparison(['协调机制'],'用户保存的比较内容',{status:'ready',cached:true});
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 const {container}=render(<Show/>);
 const table=await screen.findByRole('region',{name:'资料比较表'});
 expect(table).toHaveAttribute('tabindex','0');
 expect(screen.getByText('用户保存的比较内容')).toBeVisible();
 expect(screen.getByLabelText('比较模板')).not.toBeVisible();
 expect(container.querySelector('.kw-comparison-relations-disclosure')).not.toHaveAttribute('open');
 expect(api.compare).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'联动关系'}));
 await waitFor(()=>expect(container.querySelector('.kw-comparison-relations-disclosure')).toHaveAttribute('open'));
 expect(screen.getByRole('button',{name:'联动关系'})).toHaveAttribute('aria-expanded','true');
 fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));
 expect(screen.getByLabelText('比较模板')).toBeVisible();
 expect(api.compare).not.toHaveBeenCalled();
});

test('the compact primary action refreshes a saved explanation only after an explicit click',async()=>{
 const cached=comparison(['协调机制'],'已完成的比较',{status:'ready',cached:true});
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);api.compare.mockResolvedValue(cached);
 render(<Show/>);await screen.findByText('已完成的比较');
 expect(api.compare).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'重新深入比较'}));
 await waitFor(()=>expect(api.compare).toHaveBeenCalledWith('p1',['s1','s2'],true,expect.any(AbortSignal),[],['协调机制']));
});

test('the table fits the remaining viewport after settings and viewport height change',async()=>{
 const cached=comparison(['协调机制'],'已保存的比较',{status:'ready',cached:true});
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 const original=HTMLElement.prototype.getBoundingClientRect,height=Object.getOwnPropertyDescriptor(window,'innerHeight');
 let top=260;
 const geometry=vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  const rect=original.call(this);return this.classList.contains('kw-comparison-table-region')?{...rect,top,y:top,bottom:top+rect.height,toJSON:()=>({})}:rect;
 });
 try{
  Object.defineProperty(window,'innerHeight',{value:768,configurable:true});
  render(<Show/>);const table=await screen.findByRole('region',{name:'资料比较表'});
  await waitFor(()=>expect(table.style.maxHeight).toBe('496px'));
  top=380;fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));
  await waitFor(()=>expect(table.style.maxHeight).toBe('376px'));
  Object.defineProperty(window,'innerHeight',{value:900,configurable:true});fireEvent(window,new Event('resize'));
  await waitFor(()=>expect(table.style.maxHeight).toBe('508px'));
  expect(api.compare).not.toHaveBeenCalled();
 }finally{geometry.mockRestore();if(height)Object.defineProperty(window,'innerHeight',height)}
});

test('returning to an explicit saved comparison restores its selected cell after the comparison loads',async()=>{
 sessionStorage.clear();
 const cached=comparison(['协调机制'],'我的已保存判断',{status:'ready',cached:true});
 cached.evidence=[{id:'evidence-1',source_id:'s1',source_title:'相关论文',block_id:'b1',quote:'The original evidence.',locator:{page:3},source_version:'v1',origin:'source'}];
 cached.rows[0].values[0].evidence_ids=['evidence-1'];
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 const first=render(<Show initialId="comparison-1"/>);
 await screen.findByText('我的已保存判断');
 fireEvent.click(screen.getByRole('button',{name:'查看原文依据'}));
 expect(first.container.querySelectorAll('.kw-current-comparison-cell')).toHaveLength(1);
 first.unmount();
 const reopened=render(<Show initialId="comparison-1"/>);
 await screen.findByText('我的已保存判断');
 await waitFor(()=>expect(reopened.container.querySelectorAll('.kw-current-comparison-cell')).toHaveLength(1));
 expect(screen.getByRole('heading',{name:'当前比较项的依据'})).toBeVisible();
 expect(api.compare).not.toHaveBeenCalled();
});

test('a restored cell in a lower row and later column becomes visible inside the table without page scrolling',async()=>{
 sessionStorage.clear();
 const cached=comparison(['第一项','深行维度'],'普通比较内容',{status:'ready',cached:true});
 cached.evidence=[{id:'deep-evidence',source_id:'s2',source_title:'我的方法',block_id:'b2',quote:'The later source evidence.',locator:{page:3},source_version:'v2',origin:'source'}];
 cached.rows[1].values[1]={...cached.rows[1].values[1],text:'深行横列的个人判断',evidence_ids:['deep-evidence']};
 api.list.mockResolvedValue({items:[cached]});api.preview.mockResolvedValue(cached);
 const original=HTMLElement.prototype.getBoundingClientRect;
 const rect=(x:number,y:number,width:number,height:number)=>({x,y,width,height,top:y,left:x,right:x+width,bottom:y+height,toJSON:()=>({})});
 const readWidth=Object.getOwnPropertyDescriptor(Element.prototype,'clientWidth')?.get,readHeight=Object.getOwnPropertyDescriptor(Element.prototype,'clientHeight')?.get;
 const width=vi.spyOn(Element.prototype,'clientWidth','get').mockImplementation(function(this:Element){return this.classList.contains('kw-comparison-table-region')?500:readWidth?.call(this)||0});
 const height=vi.spyOn(Element.prototype,'clientHeight','get').mockImplementation(function(this:Element){return this.classList.contains('kw-comparison-table-region')?300:readHeight?.call(this)||0});
 const geometry=vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  if(this.classList.contains('kw-comparison-table-region'))return rect(0,180,500,300);
  if(this.tagName==='THEAD')return rect(0,180,1100,40);
  if(this.matches('tbody th'))return rect(0,220,180,140);
  if(this.classList.contains('kw-current-comparison-cell')){const table=this.closest<HTMLElement>('.kw-comparison-table-region')!;return rect(880-table.scrollLeft,1200-table.scrollTop,320,140)}
  return original.call(this);
 });
 const pageScroll=vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
 try{
  const first=render(<Show initialId="comparison-1"/>);await screen.findByText('深行横列的个人判断');
  fireEvent.click(screen.getByRole('button',{name:'查看原文依据'}));first.unmount();
  const reopened=render(<Show initialId="comparison-1"/>);await screen.findByText('深行横列的个人判断');
  const table=screen.getByRole('region',{name:'资料比较表'});
  await waitFor(()=>{expect(table.scrollTop).toBeGreaterThan(0);expect(table.scrollLeft).toBeGreaterThan(0)});
  expect(reopened.container.querySelector('.kw-current-comparison-cell')).toHaveTextContent('深行横列的个人判断');
  expect(pageScroll).not.toHaveBeenCalled();
 }finally{geometry.mockRestore();width.mockRestore();height.mockRestore();pageScroll.mockRestore()}
});

import {useState} from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeComparison from '../components/knowledge/KnowledgeComparison';
import type {KnowledgeComparison as Comparison,KnowledgeNode,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({list:vi.fn(),preview:vi.fn(),revise:vi.fn(),compare:vi.fn(),graph:vi.fn(),node:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),listKnowledgeComparisons:api.list,previewKnowledgeComparison:api.preview,reviseKnowledgeComparison:api.revise,compareKnowledgeSources:api.compare,getKnowledgeGraph:api.graph,getKnowledgeNode:api.node}));
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

test('a per-cell PATCH records the expected revision and survives automatic preview refresh',async()=>{
 let server=comparison();
 api.preview.mockImplementation(async()=>server);
 api.revise.mockImplementation(async()=>{server=comparison(['信息路径与机制'],'用户确认的跨分支信息路径',{revision:2,status:'ready',cached:true});server.rows[0].values[0].origin='user';return server});
 render(<Show/>);await screen.findByText('自动整理的机制');
 fireEvent.click(screen.getAllByRole('button',{name:'修改或补充'})[0]);
 fireEvent.change(screen.getByRole('textbox',{name:'比较内容'}),{target:{value:'用户确认的跨分支信息路径'}});
 const before=api.preview.mock.calls.length;
 fireEvent.click(screen.getByRole('button',{name:'保存修订'}));
 await waitFor(()=>expect(api.revise).toHaveBeenCalledWith('p1','comparison-1',expect.objectContaining({expected_revision:1,dimension:'信息路径与机制',source_id:'s1',text:'用户确认的跨分支信息路径'})));
 await waitFor(()=>expect(api.preview.mock.calls.length).toBeGreaterThan(before));
 await screen.findByText('用户确认的跨分支信息路径');
 expect(screen.queryByRole('textbox',{name:'比较内容'})).toBeNull();
 expect(screen.queryByText('自动整理的机制')).toBeNull();
 expect(api.compare).not.toHaveBeenCalled();
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

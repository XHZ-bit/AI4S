import {StrictMode} from 'react';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeComparison from '../components/knowledge/KnowledgeComparison';
import ComparisonOutcome from '../components/knowledge/ComparisonOutcome';
import type {KnowledgeComparison as Comparison,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({list:vi.fn(),preview:vi.fn(),compare:vi.fn(),graph:vi.fn(),evidence:vi.fn(),revise:vi.fn(),outcomes:vi.fn(),previewOutcome:vi.fn(),saveOutcome:vi.fn(),download:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual('../api/knowledge'),listKnowledgeComparisons:api.list,previewKnowledgeComparison:api.preview,compareKnowledgeSources:api.compare,getKnowledgeGraph:api.graph}));
vi.mock('../api/knowledgeComparison',async()=>({...await vi.importActual('../api/knowledgeComparison'),listComparisonEvidence:api.evidence,reviseComparisonCell:api.revise,listComparisonOutcomes:api.outcomes,previewComparisonOutcome:api.previewOutcome,saveComparisonOutcome:api.saveOutcome}));
vi.mock('../components/knowledge/KnowledgeComparisonRelations',()=>({default:()=>null}));
vi.mock('../components/workbench/Notebook',()=>({download:api.download}));
const evidence={id:'e1',source_id:'s1',source_title:'第一篇',source_version:'v1',block_id:'b1',quote:'The first source evidence.',locator:{page:4},origin:'source'};
const replacement={...evidence,id:'e2',block_id:'b2',quote:'An alternative source passage.',locator:{page:5}};
const sources:KnowledgeSource[]=['s1','s2'].map((id,i)=>({id,project_id:'p1',asset_id:id,version:'v1',title:i?'第二篇':'第一篇',filename:id+'.pdf',kind:'paper',media_type:'application/pdf',removed:false,created_at:'2026-11-16'}));
const comparison:Comparison={id:'c1',revision:1,source_ids:['s1','s2'],dimensions:['研究问题'],title:'固定比较',status:'basic',stale:false,cached:true,usage:{},errors:[],evidence:[evidence],rows:[{dimension:'研究问题',compatibility:'待核对条件',values:[{source_id:'s1',text:'第一篇的判断',node_ids:[],evidence_ids:['e1'],evidence_snapshot:[evidence],origin:'source'},{source_id:'s2',text:'第二篇的判断',node_ids:[],evidence_ids:[],origin:'inference'}]}]};
const outcome={id:'o1',title:'固定比较 · 我的比较成果',markdown:'# 我的比较成果\n保存的引用 v1',created_at:'2026-11-16T00:00:00Z',comparison_revision:1,stale:false,question:'我的问题',interpretation:'我的理解',unresolved:'尚未解决',cells:[{...comparison.rows[0].values[0],dimension:'研究问题',evidence:[evidence]}]};
const show=(onEvidence=vi.fn(),initialQuestion='')=>render(<MemoryRouter><KnowledgeComparison projectId="p1" sources={sources} comparisonId="c1" initialQuestion={initialQuestion} onComparison={vi.fn()} onNode={vi.fn()} onEvidence={onEvidence}/></MemoryRouter>);
beforeEach(()=>{
 vi.clearAllMocks();localStorage.clear();sessionStorage.clear();
 api.list.mockResolvedValue({items:[comparison]});api.preview.mockResolvedValue(comparison);api.graph.mockResolvedValue({nodes:[],edges:[]});api.evidence.mockResolvedValue({items:[evidence,replacement]});api.revise.mockResolvedValue({...comparison,revision:2});api.outcomes.mockResolvedValue({items:[]});api.previewOutcome.mockResolvedValue({...outcome,id:'preview'});api.saveOutcome.mockResolvedValue(outcome);
});

test('study template changes dimensions without generating model content',async()=>{
 show();await screen.findByText('固定比较');
 fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));
 fireEvent.change(screen.getByLabelText('比较模板'),{target:{value:'study'}});
 await waitFor(()=>expect(api.preview).toHaveBeenLastCalledWith('p1',['s1','s2'],[],expect.arrayContaining(['样本与研究对象','主要发现']),expect.any(AbortSignal),'study'));
 expect(api.compare).not.toHaveBeenCalled();
});

test('a cell can replace its evidence and explicitly confirm the judgment',async()=>{
 show();await screen.findByText('第一篇的判断');
 fireEvent.click(screen.getAllByRole('button',{name:'修改或补充'})[0]);
 const editor=within(screen.getByLabelText('修改比较内容'));
 fireEvent.click(await editor.findByText('An alternative source passage.'));
 fireEvent.click(editor.getByText('The first source evidence.'));
 fireEvent.change(editor.getByLabelText('比较内容'),{target:{value:'逐项核对后的个人判断'}});
 fireEvent.click(editor.getByText('我已对照所选原文核对这项判断'));
 fireEvent.click(editor.getByRole('button',{name:'保存修订'}));
 await waitFor(()=>expect(api.revise).toHaveBeenCalledWith('p1','c1',expect.objectContaining({source_id:'s1',expected_revision:1,text:'逐项核对后的个人判断',evidence_ids:['e2'],reviewed:true})));
});

test('independent comparison outcome is previewed, saved, reopened and exported with evidence',async()=>{
 const onEvidence=vi.fn();
 const showOutcome=()=>render(<StrictMode><MemoryRouter><ComparisonOutcome projectId="p1" comparison={comparison} sources={sources} initialQuestion="继承的研究问题" onEvidence={onEvidence}/></MemoryRouter></StrictMode>);
 const view=showOutcome();
 fireEvent.click(screen.getByText('保存我的比较成果'));
 const question=await screen.findByLabelText('比较成果研究问题');expect(question).toHaveValue('继承的研究问题');
 fireEvent.change(question,{target:{value:'两篇回答了什么？'}});
 fireEvent.change(screen.getByLabelText('比较成果我的理解'),{target:{value:'这是我的判断'}});
 const choices=within(screen.getByRole('group',{name:'选择比较内容 · 已选 0 项'}));
 fireEvent.click(choices.getByText('第一篇的判断'));
 fireEvent.click(screen.getByRole('button',{name:'预览比较成果'}));
 await screen.findByLabelText('比较成果导出预览');
 expect(api.previewOutcome).toHaveBeenCalledWith('p1','c1',expect.objectContaining({selections:[{dimension:'研究问题',source_id:'s1'}],question:'两篇回答了什么？',interpretation:'这是我的判断'}));
 expect(api.saveOutcome).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'保存比较成果'}));
 await screen.findByText('比较成果已保存，包含原文位置与版本快照');
 view.unmount();api.outcomes.mockResolvedValue({items:[outcome]});showOutcome();
 fireEvent.click(await screen.findByText('保存我的比较成果'));
 await waitFor(()=>expect(api.outcomes).toHaveBeenCalledTimes(2),{timeout:2000});
 fireEvent.click(await screen.findByRole('button',{name:/固定比较 · 我的比较成果/}));
 expect(await screen.findByLabelText('比较成果导出预览')).toHaveTextContent('保存的引用 v1');
 fireEvent.click(screen.getByRole('button',{name:'下载比较 Markdown'}));
 expect(api.download).toHaveBeenCalledWith('paperstride-comparison.md',outcome.markdown,'text/markdown;charset=utf-8');
 fireEvent.click(screen.getByRole('button',{name:'第一篇 第 4 页'}));
 expect(onEvidence).toHaveBeenCalledWith(evidence);
},30000);

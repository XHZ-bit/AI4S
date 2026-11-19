import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import ConceptCorrespondence from '../components/knowledge/ConceptCorrespondence';
import {createConceptCorrespondence, getConceptCorrespondences, reviseConceptCorrespondence,
  type ConceptCollection, type ConceptCorrespondence as Correspondence, type ConceptSide} from '../api/knowledgeConcepts';

vi.mock('../api/knowledgeConcepts', () => ({getConceptCorrespondences:vi.fn(), createConceptCorrespondence:vi.fn(), reviseConceptCorrespondence:vi.fn()}));
vi.mock('antd', () => ({Button:({children,type:_,size:__,loading:___,...props}:any) => <button {...props}>{children}</button>}));
vi.mock('../components/knowledge/KnowledgeSources', () => ({EvidenceList:({items,onOpen}:any) => <div>{items.map((item:any) => <button key={item.id} onClick={() => onOpen(item)}>{item.source_title}原文</button>)}</div>}));
const side = (id:string,label:string):ConceptSide => ({node:{id,label,summary:label+'的定义',version:1,metadata:{}} as any,
  source_id:id,source_title:id+'论文',source_version:'v1',conditions:{conditions:'一组分数'},available:true,evidence_fingerprint:'fp-'+id,
  evidence:[{id:'e-'+id,source_id:id,source_title:id+'论文',source_version:'v1',quote:'a vector of scores',locator:{page:4}} as any]});
const left=side('left','Softmax'),right=side('right','归一化指数函数');
const collection:ConceptCollection={node:left,items:[],candidates:[{side:right,reason:'双语术语候选'}],choices:[right],sources:[{id:'right',title:'right论文'}],generation:'local_rules',truncated:false};
const saved:Correspondence={id:'pair',left,right,current_left:left,current_right:right,status:'comparable',explanation:'定义可对照',revision:1,reviewed_by:'本机用户',reviewed_at:'2026-11-16',stale:false,stale_reasons:[]};
const callbacks={onEvidence:vi.fn(),onNode:vi.fn(),onSaved:vi.fn()};
const show=()=>render(<ConceptCorrespondence projectId="p" nodeId="left" {...callbacks}/>);

beforeEach(()=>{
  vi.clearAllMocks();localStorage.clear();
  vi.mocked(getConceptCorrespondences).mockResolvedValue(collection);
  vi.mocked(createConceptCorrespondence).mockResolvedValue(saved);
});

test('whole-space discovery is lazy and a personal decision includes both source versions',async()=>{
  show();
  expect(getConceptCorrespondences).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('核对跨论文概念'));
  fireEvent.click(await screen.findByRole('button',{name:'核对这两个概念'}));
  const review=within(screen.getByLabelText('概念双侧核对'));
  expect(review.getByRole('heading',{name:'Softmax'})).toBeVisible();
  expect(review.getByRole('heading',{name:'归一化指数函数'})).toBeVisible();
  fireEvent.click(review.getByRole('button',{name:'right论文原文'}));
  expect(callbacks.onEvidence).toHaveBeenCalledWith(right.evidence[0]);
  fireEvent.change(review.getByLabelText('概念核对结果'),{target:{value:'comparable'}});
  fireEvent.change(review.getByLabelText('概念核对说明'),{target:{value:'定义可对照'}});
  fireEvent.click(review.getByRole('button',{name:'保存概念核对'}));
  await screen.findByText('个人判断已保存，包含双方定义、原文位置及版本');
  expect(createConceptCorrespondence).toHaveBeenCalledWith('p','left',{
    other_node_id:'right',status:'comparable',explanation:'定义可对照',left_node_version:1,right_node_version:1,left_source_version:'v1',right_source_version:'v1',left_evidence_fingerprint:'fp-left',right_evidence_fingerprint:'fp-right',
  });
  expect(callbacks.onSaved).toHaveBeenCalledTimes(1);
});

test('an unfinished concept review returns with its own draft after source navigation',async()=>{
  const mounted=show();fireEvent.click(screen.getByText('核对跨论文概念'));
  fireEvent.click(await screen.findByRole('button',{name:'核对这两个概念'}));
  fireEvent.change(screen.getByLabelText('概念核对说明'),{target:{value:'还要核对变量维度'}});
  await waitFor(()=>expect(localStorage.getItem('paperstride:local:concept-draft:p:left')).toContain('还要核对变量维度'));
  mounted.unmount();show();
  expect(await screen.findByLabelText('概念核对说明')).toHaveValue('还要核对变量维度');
  expect(screen.getByLabelText('概念核对结果')).toHaveValue('uncertain');
  expect(createConceptCorrespondence).not.toHaveBeenCalled();
});

test('a stale record keeps its original snapshots and allows rejection when a source is unavailable',async()=>{
  const stale={...saved,stale:true,stale_reasons:['原资料版本已有变化'],current_right:{...right,available:false,evidence:[]}};
  vi.mocked(getConceptCorrespondences).mockResolvedValue({...collection,items:[stale],candidates:[]});
  vi.mocked(reviseConceptCorrespondence).mockResolvedValue({...stale,status:'rejected',revision:2});
  show();fireEvent.click(screen.getByText('核对跨论文概念'));
  fireEvent.click(await screen.findByRole('button',{name:'归一化指数函数 · 可对照'}));
  expect(screen.getByRole('option',{name:'可对照'})).toBeDisabled();
  fireEvent.click(screen.getByText('查看原判断及版本快照'));
  expect(within(screen.getByText('查看原判断及版本快照').closest('details')!).getByText('定义可对照').closest('p')).toBeVisible();
  fireEvent.change(screen.getByLabelText('概念核对结果'),{target:{value:'rejected'}});
  fireEvent.click(screen.getByRole('button',{name:'保存概念核对'}));
  await waitFor(()=>expect(reviseConceptCorrespondence).toHaveBeenCalledWith('p','left','pair',expect.objectContaining({status:'rejected',expected_revision:1})));
});

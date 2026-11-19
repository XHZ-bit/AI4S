import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import SourceCoverage from '../components/knowledge/SourceCoverage';
import {getSourceCoverage, reviewSourceCoverage, supplementSourceCoverage, type SourceCoverageData} from '../api/knowledgeCoverage';

vi.mock('../api/knowledgeCoverage', () => ({getSourceCoverage:vi.fn(),reviewSourceCoverage:vi.fn(),supplementSourceCoverage:vi.fn()}));

const evidence={id:'e',source_id:'s',source_title:'论文',block_id:'b',source_version:'v1',quote:'The method uses scaled scores.',origin:'source',locator:{page:4}};
const data:SourceCoverageData={source_id:'s',source_title:'论文',source_version:'v1',revision:0,parsed:true,semantic_node_count:1,model_available:true,
  scope:'缺项需结合原文核对，覆盖不代表科学结论完整。',items:[
    {category:'method',label:'核心方法',state:'covered',node_count:1,evidence_count:1,nodes:[{id:'n',label:'缩放点积',version:1}],evidence:[evidence],decision_stale:false},
    {category:'finding',label:'主要发现',state:'missing',node_count:0,evidence_count:0,nodes:[],evidence:[],decision_stale:false},
  ]};
const props={projectId:'p',sourceId:'s',sourceVersion:'v1',onRead:vi.fn(),onGraph:vi.fn(),onEvidence:vi.fn(),onUpdated:vi.fn()};

beforeEach(()=>{
  vi.clearAllMocks();
  vi.mocked(getSourceCoverage).mockResolvedValue(data);
});

test('opening coverage only reads saved content and exact evidence can reopen the original',async()=>{
  render(<SourceCoverage {...props}/>);
  expect(getSourceCoverage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  await screen.findByText('缩放点积');
  expect(supplementSourceCoverage).not.toHaveBeenCalled();
  expect(screen.getByText(data.scope)).toBeVisible();
  fireEvent.click(screen.getByText('查看本项原文依据',{selector:'summary'}));
  fireEvent.click(screen.getByRole('button',{name:'第 4 页'}));
  expect(props.onEvidence).toHaveBeenCalledWith(evidence);
});

test('one explicit supplement uses the source version and keeps the successful content',async()=>{
  vi.mocked(supplementSourceCoverage).mockResolvedValue({...data,revision:1,notice:'补充内容已保存'});
  render(<SourceCoverage {...props}/>);
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  fireEvent.click(await screen.findByRole('button',{name:'补充分析主要发现'}));
  await screen.findByText('补充内容已保存');
  expect(supplementSourceCoverage).toHaveBeenCalledExactlyOnceWith('p','s',{category:'finding',expected_source_version:'v1',expected_revision:0});
  expect(screen.getByText('缩放点积')).toBeVisible();
  expect(props.onUpdated).toHaveBeenCalledTimes(1);
});

test('manual not-reported judgments require a reason and remain distinct from missing extraction',async()=>{
  vi.mocked(reviewSourceCoverage).mockResolvedValue({...data,revision:1,items:[data.items[0],{...data.items[1],state:'not_reported',decision:{status:'not_reported',reason:'我检查了结果部分',reviewed_by:'本机用户',reviewed_at:'now'}}]});
  render(<SourceCoverage {...props}/>);
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  fireEvent.click(await screen.findByRole('button',{name:'记录我的判断'}));
  expect(screen.getByRole('button',{name:'保存判断'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('覆盖判断理由：主要发现'),{target:{value:'我检查了结果部分'}});
  fireEvent.click(screen.getByRole('button',{name:'保存判断'}));
  await screen.findByText('用户标记未报告');
  expect(reviewSourceCoverage).toHaveBeenCalledWith('p','s',{category:'finding',expected_source_version:'v1',expected_revision:0,status:'not_reported',reason:'我检查了结果部分'});
  expect(supplementSourceCoverage).not.toHaveBeenCalled();
});

test('failed supplement preserves already readable content and gives a retry path',async()=>{
  vi.mocked(supplementSourceCoverage).mockRejectedValue(new Error('原文已有变化，请重新读取'));
  render(<SourceCoverage {...props}/>);
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  fireEvent.click(await screen.findByRole('button',{name:'补充分析主要发现'}));
  await screen.findByText(/原文已有变化，请重新读取/);
  expect(screen.getByText('缩放点积')).toBeVisible();
  expect(screen.getByRole('button',{name:'重新读取'})).toBeEnabled();
});

test('offline coverage leaves original reading and human judgment available',async()=>{
  vi.mocked(getSourceCoverage).mockResolvedValue({...data,model_available:false});
  render(<SourceCoverage {...props}/>);
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  expect(await screen.findByRole('button',{name:'补充分析主要发现'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'阅读这份原文'}));
  expect(props.onRead).toHaveBeenCalledWith('s');
  const finding=within(screen.getByText('主要发现',{selector:'strong'}).closest('li')!);
  expect(finding.getByRole('button',{name:'记录我的判断'})).toBeEnabled();
});

test('late coverage from a previous source cannot overwrite the current one',async()=>{
  let resolve!:(value:SourceCoverageData)=>void;
  vi.mocked(getSourceCoverage).mockReturnValueOnce(new Promise(done=>{resolve=done}));
  const shown=render(<SourceCoverage {...props}/>);
  fireEvent.click(screen.getByText('检查内容覆盖与缺项',{selector:'summary'}));
  vi.mocked(getSourceCoverage).mockResolvedValue({...data,source_id:'second',items:[]});
  shown.rerender(<SourceCoverage {...props} sourceId="second"/>);
  await waitFor(()=>expect(getSourceCoverage).toHaveBeenCalledWith('p','second',expect.any(AbortSignal)));
  resolve(data);
  await waitFor(()=>expect(screen.queryByText('缩放点积')).toBeNull());
});

import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeSources,{SourceReadiness} from '../components/knowledge/KnowledgeSources';
import type {KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({upload:vi.fn(),analyze:vi.fn()}));
vi.mock('../api/knowledge',async()=>{
 const actual=await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge');
 return {...actual,uploadKnowledgeSource:api.upload,analyzeKnowledgeSource:api.analyze};
});
vi.mock('../api/client',()=>({apiGet:vi.fn(async()=>[])}));
vi.mock('../components/workbench/ProjectWorkbench',()=>({default:()=>null}));
vi.mock('../components/workspace/PdfReader',()=>({default:()=>null}));
const source:KnowledgeSource={id:'s',project_id:'p',asset_id:'a',version:'v1',title:'Real source',filename:'paper.md',kind:'report',media_type:'text/markdown',removed:false,created_at:'2026-11-12',availability:{original:true,parsed:true,blocks:5,semantic_nodes:0,parse_partial:true},analysis:{id:'r',project_id:'p',source_id:'s',status:'partial',stages:{save:'done',parse:'partial',extract:'partial',graph:'done'},progress:1,errors:['模型暂不可用'],warnings:[],usage:{},created_at:'',updated_at:''}};
beforeEach(()=>vi.clearAllMocks());

test('available partial results stay behind one compact disclosure',()=>{
 render(<SourceReadiness source={source}/>);
 expect(screen.getByText('部分分析完成',{selector:'summary'})).toBeVisible();
 expect(screen.getByText('可阅读')).not.toBeVisible();
 fireEvent.click(screen.getByText('部分分析完成',{selector:'summary'}));
 expect(screen.getByText('可阅读')).toBeVisible();
 expect(screen.getByText('部分可用 · 5 个内容块')).toBeVisible();
 expect(screen.getByText('尚未生成')).toBeVisible();
 expect(screen.getByText('模型暂不可用')).toBeVisible();
});

test('saved but unscheduled upload refreshes the list and never asks to retransmit',async()=>{
 api.upload.mockResolvedValue({source,analysis:source.analysis,scheduled:false,notice:'分析队列已满，原文已保存'});
 const updated=vi.fn();
 render(<MemoryRouter><KnowledgeSources projectId="p" sources={[]} onUpdated={updated} onRead={vi.fn()} onGraph={vi.fn()}/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('上传研究资料'),{target:{files:[new File(['content'],'paper.md',{type:'text/markdown'})]}});
 expect(await screen.findByRole('status')).toHaveTextContent('原文已保存；paper.md 的分析暂未开始');
 expect(updated).toHaveBeenCalled();
 expect(api.upload).toHaveBeenCalledTimes(1);
 expect(screen.queryByText('操作未完成')).toBeNull();
});

test('a later upload failure does not hide already saved files',async()=>{
 api.upload.mockResolvedValueOnce({source,analysis:source.analysis,scheduled:true}).mockRejectedValueOnce(new Error('第二份文件格式有误'));
 const updated=vi.fn();
 render(<MemoryRouter><KnowledgeSources projectId="p" sources={[]} onUpdated={updated} onRead={vi.fn()} onGraph={vi.fn()}/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('上传研究资料'),{target:{files:[new File(['one'],'one.md'),new File(['two'],'two.md')]}});
 await screen.findByText('第二份文件格式有误');
 expect(updated.mock.calls.length).toBeGreaterThanOrEqual(2);
 expect(api.upload).toHaveBeenCalledTimes(2);
});

test('continuation is named accurately and uses the existing resumable endpoint',async()=>{
 api.analyze.mockResolvedValue({...source.analysis,status:'queued'});
 const updated=vi.fn();
 render(<MemoryRouter><KnowledgeSources projectId="p" sources={[source]} onUpdated={updated} onRead={vi.fn()} onGraph={vi.fn()}/></MemoryRouter>);
 expect(screen.queryByRole('button',{name:'重新分析'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'继续知识分析'}));
 await waitFor(()=>expect(api.analyze).toHaveBeenCalledWith('p','s',true));
 expect(updated).toHaveBeenCalled();
});

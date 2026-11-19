import {useState} from 'react';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import LearningProgress from '../components/knowledge/LearningProgress';
import {getNodeProgress,getNodeSummary,explainNodeSummary,getProjectLearningSummary,explainProjectLearningSummary,saveNodeProgress,type NodeSummary} from '../api/knowledgeExperience';

vi.mock('../api/knowledgeExperience',()=>({getNodeProgress:vi.fn(),getNodeSummary:vi.fn(),explainNodeSummary:vi.fn(),getProjectLearningSummary:vi.fn(),explainProjectLearningSummary:vi.fn(),saveNodeProgress:vi.fn()}));
const summary=(node='n',recommendation='先回顾这个节点的定义。'):NodeSummary=>({progress:{node_id:node,status:'in_progress',version:1},run_count:1,recent_runs:[{id:'run',practice_id:'practice',status:'success',created_at:'2026-11-17'}],recommendation,scope:'当前节点的已保存运行记录'});
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done});return{promise,resolve}}
beforeEach(()=>{
 vi.clearAllMocks();
 vi.mocked(getNodeProgress).mockImplementation(async(_p,node)=>({node_id:node,status:'in_progress',version:3}));
 vi.mocked(getNodeSummary).mockImplementation(async(_p,node)=>summary(node));
 vi.mocked(saveNodeProgress).mockResolvedValue({node_id:'n',status:'understood',version:4});
});
function Dock(){
 const [visible,setVisible]=useState(false);
 return <LearningProgress projectId="p" nodeId="n" variant="dock" summaryVisible={visible} onOpenSummary={()=>setVisible(true)}>
  <div role="tablist" aria-label="学习工具"><button id="kw-learning-tool-records-tab" role="tab" onClick={()=>setVisible(true)}>学习记录</button><button role="tab" onClick={()=>setVisible(false)}>笔记</button></div>
  <textarea aria-label="保留中的个人笔记"/>
 </LearningProgress>;
}

test('the dock keeps self-assessment and its direct summary entry visible without automatic advice',async()=>{
 render(<Dock/>);
 const state=await screen.findByRole('combobox',{name:'我的学习状态'});
 await waitFor(()=>expect(state).toBeEnabled());
 expect(state).toHaveValue('in_progress');
 expect(within(state).getAllByRole('option').map(option=>option.textContent)).toEqual(['待学习','学习中','自评理解','需复习']);
 expect(screen.getByRole('button',{name:'查看学习小结'})).toBeVisible();
 expect(document.getElementById('kw-learning-tool-records-panel')).toHaveAttribute('hidden');
 expect(getNodeSummary).not.toHaveBeenCalled();
 expect(explainNodeSummary).not.toHaveBeenCalled();
 expect(explainProjectLearningSummary).not.toHaveBeenCalled();
 expect(saveNodeProgress).not.toHaveBeenCalled();
});

test('one summary action opens the records tab, reads once, and preserves a sibling note draft',async()=>{
 const response=deferred<NodeSummary>();vi.mocked(getNodeSummary).mockReturnValueOnce(response.promise);
 render(<Dock/>);
 fireEvent.change(screen.getByRole('textbox',{name:'保留中的个人笔记'}),{target:{value:'尚未保存的阅读判断'}});
 fireEvent.click(screen.getByRole('button',{name:'查看学习小结'}));
 await waitFor(()=>expect(getNodeSummary).toHaveBeenCalledTimes(1));
 const panel=screen.getByRole('tabpanel',{name:'学习记录'});
 expect(panel).toBeVisible();
 await act(async()=>{response.resolve(summary())});
 expect(within(panel).getByText('先回顾这个节点的定义。')).toBeVisible();
 expect(within(panel).getByText('自评记录与论文审核状态分别保存。')).not.toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'笔记'}));
 expect(panel).not.toBeVisible();
 expect(screen.getByRole('textbox',{name:'保留中的个人笔记'})).toHaveValue('尚未保存的阅读判断');
 expect(screen.getByRole('combobox',{name:'我的学习状态'})).toBeVisible();
 expect(explainNodeSummary).not.toHaveBeenCalled();
});

test('opening the records tab directly only reads existing records and shows model scope on demand',async()=>{
 render(<LearningProgress projectId="p" nodeId="n" variant="dock" summaryVisible><button id="kw-learning-tool-records-tab">学习记录</button></LearningProgress>);
 const panel=screen.getByRole('tabpanel',{name:'学习记录'});
 await within(panel).findByText('先回顾这个节点的定义。');
 expect(getNodeSummary).toHaveBeenCalledTimes(1);
 expect(explainNodeSummary).not.toHaveBeenCalled();
 const scope=within(panel).getByText('将当前节点、近期运行状态和最多 5 条经验的片段发送给所选模型。');
 expect(scope).not.toBeVisible();
 fireEvent.click(within(panel).getByText('AI 建议使用说明',{selector:'summary'}));
 expect(scope).toBeVisible();
 vi.mocked(explainNodeSummary).mockResolvedValue({...summary(),explanation:'由用户主动请求的学习建议。'});
 fireEvent.click(within(panel).getByRole('button',{name:'生成 AI 学习建议'}));
 await within(panel).findByText('由用户主动请求的学习建议。');
 expect(explainNodeSummary).toHaveBeenCalledWith('p','n');
});

test('the dock saves only an explicit self-assessment with the current version and visible feedback',async()=>{
 render(<LearningProgress projectId="p" nodeId="n" variant="dock" summaryVisible={false}/>);
 const state=screen.getByRole('combobox',{name:'我的学习状态'});
 await waitFor(()=>expect(state).toBeEnabled());
 fireEvent.change(state,{target:{value:'understood'}});
 await screen.findByText('学习状态已保存：自评理解');
 expect(saveNodeProgress).toHaveBeenCalledWith('p','n','understood',3);
 expect(state).toHaveValue('understood');
 expect(getNodeSummary).not.toHaveBeenCalled();
 expect(explainNodeSummary).not.toHaveBeenCalled();
});

test('a late summary from another node cannot replace the current node records',async()=>{
 const first=deferred<NodeSummary>(),second=deferred<NodeSummary>();
 vi.mocked(getNodeSummary).mockImplementation((_p,node)=>node==='first'?first.promise:second.promise);
 const props={projectId:'p',variant:'dock' as const,summaryVisible:true};
 const {rerender}=render(<LearningProgress {...props} nodeId="first"/>);
 await waitFor(()=>expect(getNodeSummary).toHaveBeenCalledWith('p','first'));
 rerender(<LearningProgress {...props} nodeId="second"/>);
 await waitFor(()=>expect(getNodeSummary).toHaveBeenCalledWith('p','second'));
 await act(async()=>{second.resolve(summary('second','第二个节点的记录。'))});
 await screen.findByText('第二个节点的记录。');
 await act(async()=>{first.resolve(summary('first','第一个节点的旧响应。'))});
 expect(screen.getByText('第二个节点的记录。')).toBeVisible();
 expect(screen.queryByText('第一个节点的旧响应。')).toBeNull();
});

test('an unavailable summary can be retried without generating advice',async()=>{
 vi.mocked(getNodeSummary).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(summary());
 render(<Dock/>);
 fireEvent.click(screen.getByRole('button',{name:'查看学习小结'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('记录读取失败，请重试。');
 fireEvent.click(screen.getByRole('button',{name:'查看学习小结'}));
 await screen.findByText('先回顾这个节点的定义。');
 expect(getNodeSummary).toHaveBeenCalledTimes(2);
 expect(getProjectLearningSummary).not.toHaveBeenCalled();
 expect(explainNodeSummary).not.toHaveBeenCalled();
});

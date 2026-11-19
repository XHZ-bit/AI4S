import {fireEvent,render,screen,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import NodeQuestion from '../components/knowledge/NodeQuestion';
import LearningProgress from '../components/knowledge/LearningProgress';
import {askKnowledgeNode,getNodeProgress,getNodeSummary,getProjectLearningSummary,type NodeAnswer,type NodeSummary,type ProjectLearningSummary,type SavedLearningExperience} from '../api/knowledgeExperience';

vi.mock('../api/knowledgeExperience',()=>({askKnowledgeNode:vi.fn(),getNodeProgress:vi.fn(),getNodeSummary:vi.fn(),getProjectLearningSummary:vi.fn(),explainNodeSummary:vi.fn(),explainProjectLearningSummary:vi.fn(),saveNodeProgress:vi.fn()}));
const mechanism='当前展示节点及原文摘录，尚未生成针对问题的解释。';
const base:NodeAnswer={answer:'节点说明与引用片段。',origin:'source',citations:[],node_ids:['n'],edge_ids:[],model_used:false,warnings:[mechanism]};
const experiences:SavedLearningExperience[]=[
 {id:'a',node_id:'n',practice_id:'p',content:'我保存的第一条分析。',origin:'user_saved_ai_feedback',created_at:'2026-11-17T01:00:00Z'},
 {id:'b',node_id:'n',practice_id:'p',content:'我保存的第二条分析。',origin:'user_saved_ai_feedback',created_at:'2026-11-17T02:00:00Z'},
];
beforeEach(()=>{
 vi.clearAllMocks();
 vi.mocked(askKnowledgeNode).mockResolvedValue(base);
 vi.mocked(getNodeProgress).mockResolvedValue({node_id:'n',status:'not_started',version:1});
});
async function ask(){
 fireEvent.change(screen.getByLabelText('节点问题'),{target:{value:'这一步的原文是什么？'}});
 fireEvent.click(screen.getByRole('button',{name:'结合图谱与原文回答'}));
 await screen.findByText(base.answer);
}

test('retrieved excerpts retain their origin while routine explanation stays folded',async()=>{
 render(<NodeQuestion projectId="p" nodeId="n"/>);
 expect(askKnowledgeNode).not.toHaveBeenCalled();
 expect(screen.getByText(/按平台预算生成回答/)).not.toBeVisible();
 await ask();
 expect(screen.getByText('原文摘录')).toBeVisible();
 expect(screen.queryByText('AI 辅助回答')).not.toBeInTheDocument();
 expect(screen.getByText(mechanism)).not.toBeVisible();
 fireEvent.click(screen.getByText('回答说明',{selector:'summary'}));
 expect(screen.getByText(mechanism)).toBeVisible();
});

test('model failures, changed sources and unknown warnings remain visible outside the disclosure',async()=>{
 const warnings=[mechanism,'模型请求失败，已保留原文。','生成期间来源已更新，请重新提问核对','缺少足够依据，需核对适用条件。'];
 vi.mocked(askKnowledgeNode).mockResolvedValue({...base,warnings});
 render(<NodeQuestion projectId="p" nodeId="n"/>);
 await ask();
 for(const warning of warnings.slice(1)){
  const element=screen.getByText(warning);
  expect(element).toBeVisible();
  expect(element.closest('details')).toBeNull();
 }
 expect(screen.getByText(mechanism)).not.toBeVisible();
});

test('a generated answer is labeled AI and an inferred saved node is not called original text',async()=>{
 vi.mocked(askKnowledgeNode).mockResolvedValueOnce({...base,model_used:true,origin:'inference',warnings:[]}).mockResolvedValueOnce({...base,model_used:false,origin:'inference',warnings:[]});
 const {rerender}=render(<NodeQuestion projectId="p" nodeId="n"/>);
 await ask();
 expect(screen.getByText('AI 辅助回答')).toBeVisible();
 expect(screen.queryByText('原文摘录')).not.toBeInTheDocument();
 rerender(<NodeQuestion projectId="p" nodeId="other"/>);
 await ask();
 expect(screen.getByText('已保存内容摘录')).toBeVisible();
 expect(screen.queryByText('AI 辅助回答')).not.toBeInTheDocument();
 expect(screen.queryByText('原文摘录')).not.toBeInTheDocument();
});

test('node learning records identify AI origin once per group and retain each date and content',async()=>{
 vi.mocked(getNodeSummary).mockResolvedValue({progress:{node_id:'n',status:'not_started',version:1},run_count:0,recent_runs:[],recommendation:'按需选择下一项。',scope:'当前节点',saved_experiences:experiences} as NodeSummary);
 render(<LearningProgress projectId="p" nodeId="n"/>);
 fireEvent.click(screen.getByText('查看学习小结',{selector:'button'}));
 const heading=await screen.findByText('AI 学习记录（2）',{selector:'summary'});
 const details=heading.closest('details')!;
 fireEvent.click(heading);
 expect(within(details).getByText('由你保存，供回顾与核对。')).toBeVisible();
 for(const entry of experiences){expect(within(details).getByText(entry.content)).toBeVisible();expect(within(details).getByText(entry.created_at)).toBeVisible();}
 expect(screen.queryByText(/用户保存的 AI 分析 ·/)).not.toBeInTheDocument();
 expect(screen.getByText('自评记录与论文审核状态分别保存。')).toBeVisible();
});

test('workspace learning records use the same concise group and keep the node self-assessment',async()=>{
 vi.mocked(getProjectLearningSummary).mockResolvedValue({scope:'当前空间',truncated:false,items:[{node_id:'n',node_label:'点积',status:'review',run_count:1,recommendation:'回顾定义。',saved_experiences:experiences}]} as ProjectLearningSummary);
 render(<LearningProgress projectId="p" nodeId="n" onNode={vi.fn()}/>);
 fireEvent.click(screen.getByText('查看阶段记录',{selector:'button'}));
 const section=await screen.findByRole('region',{name:'阶段学习记录'});
 expect(section).toHaveTextContent('需复习');
 const heading=within(section).getByText('AI 学习记录（2）',{selector:'summary'});
 fireEvent.click(heading);
 for(const entry of experiences)expect(within(section).getByText(entry.content)).toBeVisible();
 expect(within(section).queryByText(/用户保存的 AI 分析 ·/)).not.toBeInTheDocument();
});

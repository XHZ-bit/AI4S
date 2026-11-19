import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import TaskGuidance from '../components/knowledge/TaskGuidance';
import {getLearningProgress, getNodeSummary} from '../api/knowledgeExperience';
import {getCheckRecommendation} from '../api/knowledgeChecks';
import {readWorkspaceResume, writeWorkspaceResume} from '../components/knowledge/workspaceResume';
import type {KnowledgeGraph, KnowledgeSource} from '../api/knowledge';
import type {SavedLearningRoute} from '../api/knowledgeRoutes';

vi.mock('../api/knowledgeExperience', () => ({getLearningProgress: vi.fn(), getNodeSummary: vi.fn()}));
vi.mock('../api/knowledgeChecks',()=>({getCheckRecommendation:vi.fn()}));
const source = {id:'s', title:'Attention', version:'v2'} as KnowledgeSource;
const graph = {nodes:[{id:'n', label:'缩放点积', summary:'注意力的缩放', kind:'formula', metadata:{}, source_id:'s', evidence_ids:['e']}], edges:[]} as unknown as KnowledgeGraph;
const props = {projectId:'p',question:'注意力缩放',graph,sources:[source],onResume:vi.fn(),onLearn:vi.fn(),onRead:vi.fn(),onImport:vi.fn()};

beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks();
  vi.mocked(getLearningProgress).mockResolvedValue({items:[]});
  vi.mocked(getCheckRecommendation).mockResolvedValue({recommendation:null});
});

test('a saved question resumes its exact source position and warns about a changed version', async () => {
  const resume={projectId:'p',title:'空间',url:'/research/p?view=reading&source=s&page=4',view:'reading' as const,question:'注意力',sourceId:'s',sourceVersion:'v1',sourceTitle:'Attention',page:'4',unresolvedQuestions:'4.0 是概率吗？'};
  render(<TaskGuidance {...props} resume={resume}/>);
  expect(screen.getByText('4.0 是概率吗？')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('资料已有变化');
  fireEvent.click(screen.getByRole('button',{name:'继续上次任务'}));
  expect(props.onResume).toHaveBeenCalledWith(resume.url);
  fireEvent.click(screen.getByRole('button',{name:'换一个起点'}));
  await screen.findByRole('button',{name:'理解这个知识点'});
  expect(getNodeSummary).not.toHaveBeenCalled();
});

test('self-assessed understood knowledge is skipped and reading remains available', async () => {
  vi.mocked(getLearningProgress).mockResolvedValue({items:[{node_id:'n',status:'understood',version:1}]});
  render(<TaskGuidance {...props}/>);
  await screen.findByRole('button',{name:'打开原文'});
  fireEvent.click(screen.getByRole('button',{name:'打开原文'}));
  expect(props.onRead).toHaveBeenCalledWith('s');
});

test('review uses an existing prerequisite recommendation without generating new advice', async () => {
  vi.mocked(getLearningProgress).mockResolvedValue({items:[{node_id:'n',status:'review',version:1}]});
  vi.mocked(getNodeSummary).mockResolvedValue({suggested_node:{id:'dot',label:'向量点积'}} as never);
  render(<TaskGuidance {...props}/>);
  await screen.findByText('向量点积');
  fireEvent.click(screen.getByRole('button',{name:'理解这个知识点'}));
  expect(props.onLearn).toHaveBeenCalledWith('dot');
  await waitFor(()=>expect(getNodeSummary).toHaveBeenCalledTimes(1));
});

test('task snapshots are isolated by account and project and reject external resume URLs', () => {
  const task={projectId:'p',title:'Attention',url:'/research/p?view=learning&node=n',view:'learning' as const,question:'缩放',unresolvedQuestions:'为什么？'};
  expect(writeWorkspaceResume('a',task)).toBe(true);
  expect(readWorkspaceResume('a','p')).toEqual(task);
  expect(readWorkspaceResume('b','p')).toBeUndefined();
  expect(readWorkspaceResume('a','other')).toBeUndefined();
  writeWorkspaceResume('a',{...task,url:'https://example.com/research/p'});
  expect(readWorkspaceResume('a','p')).toBeUndefined();
});

test('a specific saved misconception offers the relevant foundation and can be skipped',async()=>{
  vi.mocked(getCheckRecommendation).mockResolvedValue({recommendation:{attempt_id:'check',node_id:'softmax',label:'Softmax',source_node_id:'n',source_node_label:'缩放点积',question:'4.0是概率吗？',answer:'是概率',reason:'先区分缩放分数和权重。'}});
  render(<TaskGuidance {...props}/>);
  fireEvent.click(await screen.findByRole('button',{name:'补充这一项理解'}));
  expect(props.onLearn).toHaveBeenCalledWith('softmax');
  fireEvent.click(screen.getByRole('button',{name:'换一个起点'}));
  await screen.findByRole('button',{name:'理解这个知识点'});
});

test('a saved route resumes the next valid step before a generic browser location',async()=>{
  const route = {id:'r',target_label:'理解注意力',steps:[{node_id:'dot',label:'点积',available:true,stale:false}],next_node_id:'dot',question_changed:false,stale:false} as SavedLearningRoute;
  const onRoute=vi.fn();
  render(<TaskGuidance {...props} learningRoute={route} onRoute={onRoute}/>);
  fireEvent.click(await screen.findByRole('button',{name:'继续路线学习'}));
  expect(props.onLearn).toHaveBeenCalledWith('dot');
  fireEvent.click(screen.getByRole('button',{name:'查看与调整路线'}));
  expect(onRoute).toHaveBeenCalledOnce();
});

test('a changed research question asks to review the route without claiming it is current',async()=>{
  const route = {id:'r',target_label:'旧目标',steps:[],next_node_id:null,question_changed:true,stale:true} as unknown as SavedLearningRoute;
  const onRoute=vi.fn();
  render(<TaskGuidance {...props} learningRoute={route} onRoute={onRoute}/>);
  fireEvent.click(await screen.findByRole('button',{name:'核对学习路线'}));
  expect(onRoute).toHaveBeenCalledOnce();
  expect(screen.queryByRole('button',{name:'继续路线学习'})).toBeNull();
});

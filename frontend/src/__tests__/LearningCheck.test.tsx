import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import LearningCheck from '../components/knowledge/LearningCheck';
import {answerNodeCheck, dismissNodeCheck, getNodeChecks} from '../api/knowledgeChecks';
import FormulaContext from '../components/knowledge/FormulaContext';
import {incompleteFormulaText} from '../components/knowledge/KnowledgeText';

vi.mock('../api/knowledgeChecks', () => ({getNodeChecks:vi.fn(),answerNodeCheck:vi.fn(),dismissNodeCheck:vi.fn()}));
const question={id:'attention_score',version:1,title:'分数与权重',question:'4.0是概率吗？',choices:[{id:'probability',text:'它是概率'},{id:'score',text:'它是缩放分数'}]};
const attempt={id:'attempt',node_id:'n',question:question.question,answer:'它是概率',correct:false,feedback:'先补充softmax。',explanation:'我的理由',stale:false,dismissed:false,created_at:'2026-11-16'};
beforeEach(()=>{
  vi.clearAllMocks();
  vi.mocked(getNodeChecks).mockResolvedValue({questions:[question],history:[],context_fingerprint:'version1',available:true});
  vi.mocked(answerNodeCheck).mockResolvedValue(attempt);
  vi.mocked(dismissNodeCheck).mockResolvedValue({dismissed:true});
});

test('checks load on request and save the selected answer with its context', async()=>{
  render(<LearningCheck projectId="p" nodeId="n"/>);
  expect(getNodeChecks).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('用一个问题检验理解'));
  fireEvent.click(await screen.findByLabelText('它是概率'));
  fireEvent.change(screen.getByLabelText('教学检查我的理由'),{target:{value:'我的理由'}});
  fireEvent.click(screen.getByRole('button',{name:'保存回答并看建议'}));
  await screen.findByText('可以从这里继续理解');
  expect(answerNodeCheck).toHaveBeenCalledWith('p','n','attention_score',{answer_id:'probability',expected_context:'version1',explanation:'我的理由'});
  fireEvent.click(screen.getByRole('button',{name:'这条建议不适合我'}));
  await waitFor(()=>expect(dismissNodeCheck).toHaveBeenCalledWith('p','n','attempt'));
});

test('historical answers survive source changes while new answers are disabled', async()=>{
  vi.mocked(getNodeChecks).mockResolvedValue({questions:[question],history:[{...attempt,stale:true}],context_fingerprint:'v2',available:false});
  render(<LearningCheck projectId="p" nodeId="n"/>);
  fireEvent.click(screen.getByText('用一个问题检验理解'));
  await screen.findByLabelText('它是概率');
  expect(screen.getByRole('button',{name:'保存回答并看建议'})).toBeDisabled();
  fireEvent.click(screen.getByText('我的回答记录 · 1'));
  expect(screen.getByText('知识或依据已变化，保留当时的回答。')).toBeVisible();
});

test('formula symbol descriptions show recorded dimensions and leave missing meanings explicit',()=>{
  render(<FormulaContext metadata={{symbols:{Q:{meaning:'查询矩阵',shape:'n × d_k'},K:{unit:'无量纲'}},conditions:['固定教学输入']}}/>);
  expect(screen.getByText('查询矩阵')).toBeVisible();
  expect(screen.getByText('n × d_k')).toBeVisible();
  expect(screen.getByText('含义尚待对照原文')).toBeVisible();
  expect(screen.getByText('固定教学输入')).toBeVisible();
});

test('a truncated equation is identified without treating intact prose as a broken formula',()=>{
  expect(incompleteFormulaText('Attention(Q, K, V) = softmax(QKT')).toBe(true);
  expect(incompleteFormulaText('Attention(Q, K, V) = softmax(QKT)')).toBe(false);
  expect(incompleteFormulaText('条件为 x=2，结合当前定义解释输入。')).toBe(false);
});

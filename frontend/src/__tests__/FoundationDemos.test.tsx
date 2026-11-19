import {fireEvent, render, screen, within} from '@testing-library/react';
import {expect, test, vi} from 'vitest';
import KnowledgeDemos from '../components/knowledge/KnowledgeDemos';
import {stableSoftmax} from '../components/knowledge/FoundationDemos';

test('softmax handles large finite scores and preserves a common shift', () => {
  const expected = stableSoftmax([4, 2, 0]);
  expect(expected[0]).toBeCloseTo(0.8668133322, 8);
  expect(expected.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 12);
  expect(stableSoftmax([1004, 1002, 1000])).toEqual(expected);
  expect(stableSoftmax([])).toEqual([]);
  expect(stableSoftmax([Infinity])).toEqual([]);
});

test('attention shows the pre-softmax score separately from the final weights', () => {
  render(<KnowledgeDemos ids={['scaled_attention']}/>);
  expect(screen.getByTestId('scaled-score-0')).toHaveTextContent('4.0000');
  expect(screen.getByRole('table')).toHaveTextContent('0.8668');
  fireEvent.change(screen.getByRole('spinbutton', {name: '键向量维度 d_k'}), {target:{value:'16'}});
  expect(screen.getByTestId('scaled-score-0')).toHaveTextContent('2.0000');
  expect(screen.getByRole('status')).toHaveTextContent('1.0000');
});

test('dot-product inputs change a visible per-dimension calculation', () => {
  render(<KnowledgeDemos ids={['dot_product']}/>);
  expect(screen.getByRole('status')).toHaveTextContent('8.000');
  fireEvent.change(screen.getByRole('spinbutton', {name:'查询分量 q1'}), {target:{value:'0'}});
  expect(screen.getByRole('status')).toHaveTextContent('6.000');
});

test('a probability draw preserves counts and rejects an empty bag', () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0.1);
  try {
    render(<KnowledgeDemos ids={['probability']}/>);
    fireEvent.click(screen.getByRole('button', {name:'有放回抽取12次'}));
    expect(screen.getByRole('status')).toHaveTextContent('共 12 次');
    const red = screen.getByRole('row', {name:/红球/});
    expect(within(red).getAllByRole('cell').map(cell=>cell.textContent)).toEqual(['0.5000','12','1.0000']);
    for (const label of ['红球数量', '蓝球数量', '白球数量']) {
      fireEvent.change(screen.getByRole('spinbutton', {name:label}), {target:{value:'0'}});
    }
    expect(screen.queryByRole('button', {name:'有放回抽取12次'})).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('至少需要1个球');
  } finally { random.mockRestore(); }
});

test('research design distinguishes timing differences from group allocation', () => {
  render(<KnowledgeDemos ids={['research_design']}/>);
  const feedback = within(screen.getByRole('region', {name:'研究条件反馈'}));
  expect(feedback.getByText(/学习时长不同/)).toBeVisible();
  fireEvent.change(screen.getByRole('spinbutton', {name:'回忆组学习分钟'}), {target:{value:'5'}});
  expect(feedback.queryByText(/学习时长不同/)).toBeNull();
  fireEvent.change(screen.getByLabelText('回忆组测试间隔'), {target:{value:'即时'}});
  fireEvent.change(screen.getByLabelText('进入各组的方式'), {target:{value:'随机'}});
  expect(feedback.getByText('列出的时间条件已对齐，分组采用随机分配。')).toBeVisible();
  expect(feedback.getByText(/统计不确定性/)).toBeVisible();
});

test('sampling keeps support and sample counts within the stated population', () => {
  render(<KnowledgeDemos ids={['sampling']}/>);
  expect(screen.getByRole('status')).toHaveTextContent('30.0%');
  fireEvent.change(screen.getByRole('spinbutton', {name:'总体人数 N'}), {target:{value:'20'}});
  expect(screen.getByRole('spinbutton', {name:'实际样本量 n'})).toHaveValue('20');
  expect(screen.getByRole('spinbutton', {name:'样本中支持人数 k'})).toHaveValue('20');
  expect(screen.getByRole('status')).toHaveTextContent('100.0%');
  fireEvent.change(screen.getByLabelText('抽样方式'), {target:{value:'random'}});
  expect(screen.getByRole('region', {name:'抽样范围反馈'})).toHaveTextContent('随机抽取');
});

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import LearningRouteContinue from '../components/knowledge/LearningRouteContinue';
import {notifyLearningRoute, updateLearningRoute, type SavedLearningRoute} from '../api/knowledgeRoutes';

vi.mock('../api/knowledgeRoutes', () => ({updateLearningRoute: vi.fn(), notifyLearningRoute: vi.fn()}));
const route = {id:'r',revision:4,target_label:'理解注意力',next_node_id:'dot',question_changed:false,stale:false,
  steps:[{node_id:'dot',label:'点积',state:'todo',available:true,stale:false},{node_id:'goal',label:'注意力',state:'todo',available:true,stale:false}]} as SavedLearningRoute;
const props = {projectId:'p',nodeId:'dot',route,loading:false,onChanged:vi.fn(),onLearn:vi.fn(),onRoute:vi.fn()};
beforeEach(() => {vi.clearAllMocks();});

test('one explicit completion persists the current step and opens the server-selected next step',async()=>{
  const next={...route,revision:5,next_node_id:'goal'};
  vi.mocked(updateLearningRoute).mockResolvedValue({route:next});
  render(<LearningRouteContinue {...props}/>);
  expect(updateLearningRoute).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'完成这一步并继续'}));
  await waitFor(()=>expect(updateLearningRoute).toHaveBeenCalledWith('p',{expected_revision:4,step_node_id:'dot',state:'done'}));
  await waitFor(()=>expect(props.onLearn).toHaveBeenCalledWith('goal'));
  expect(props.onChanged).toHaveBeenCalledWith(next);
  expect(notifyLearningRoute).toHaveBeenCalledWith('p');
});

test('a conflicting completion preserves the reading location and provides a review action',async()=>{
  vi.mocked(updateLearningRoute).mockRejectedValue(Object.assign(new Error('changed'),{status:409}));
  render(<LearningRouteContinue {...props}/>);
  fireEvent.click(screen.getByRole('button',{name:'完成这一步并继续'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('当前阅读位置保留');
  expect(props.onLearn).not.toHaveBeenCalled();
  expect(props.onChanged).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'核对学习路线'}));
  expect(props.onRoute).toHaveBeenCalledOnce();
});

test('a changed question or missing prerequisite requests review before completion',()=>{
  render(<LearningRouteContinue {...props} route={{...route,needs_replan:true}}/>);
  expect(screen.queryByRole('button',{name:'完成这一步并继续'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'核对学习路线'}));
  expect(props.onRoute).toHaveBeenCalledOnce();
  expect(updateLearningRoute).not.toHaveBeenCalled();
});

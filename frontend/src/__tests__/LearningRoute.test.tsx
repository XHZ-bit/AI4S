import {useState} from 'react';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, expect, test, vi} from 'vitest';
import LearningRoute from '../components/knowledge/LearningRoute';
import * as api from '../api/knowledgeRoutes';
import {getKnowledgeGraph, type KnowledgeEvidence, type KnowledgeGraph, type KnowledgeNode} from '../api/knowledge';

vi.mock('../api/knowledgeRoutes', () => ({previewLearningRoute: vi.fn(), saveLearningRoute: vi.fn(), updateLearningRoute: vi.fn(), recheckLearningRoute: vi.fn(), getLearningRouteHistory: vi.fn(), notifyLearningRoute: vi.fn()}));
vi.mock('../api/knowledge', () => ({getKnowledgeGraph: vi.fn()}));
const node = {id: 'goal', label: '理解缩放注意力', summary: '缩放分数在softmax之前', kind: 'formula', source_id: 's', evidence_ids: ['e'], metadata: {}, version: 1} as unknown as KnowledgeNode;
const foundation = {...node, id: 'dot', label: '向量点积', kind: 'concept'};
const evidence = {id: 'e', source_id: 's', source_title: '教学资料', source_version: 'v1', block_id: 'b', quote: '先计算点积，再缩放分数。', locator: {heading: '方法'}} as KnowledgeEvidence;
const graph = {nodes: [foundation, node], edges: [], total_nodes: 2, total_edges: 0, truncated: false} as KnowledgeGraph;
function step(n: KnowledgeNode, role: 'target' | 'prerequisite'): api.LearningRouteStep {
  return {node_id: n.id, label: n.label, role, state: 'todo', snapshot: {node: n, source: {id: 's', title: '教学资料', version: 'v1'}, evidence: [evidence], prerequisites: []}, available: true, stale: false, stale_reasons: [], current_context: n.id + '-context', current_node: n, current_evidence: [evidence], current_source: {id: 's', title: '教学资料', version: 'v1'}};
}
const preview: api.LearningRoutePreview = {target_node_id: node.id, target_label: node.label, research_question: '为什么缩放？', preview_fingerprint: 'fp', steps: [step(foundation, 'prerequisite'), step(node, 'target')], edges: [], warnings: [], cycle_detected: false, truncated: false, graph};
const saved: api.SavedLearningRoute = {...preview, id: 'route', revision: 1, created_at: '2026-11-16', updated_at: '2026-11-16', reviewed_by: 'user', stale: false, question_changed: false, next_node_id: 'dot'};
const props = {projectId: 'p', initialNode: node, loading: false, onChanged: vi.fn(), onReload: vi.fn(), onLearn: vi.fn(), onGraph: vi.fn(), onEvidence: vi.fn()};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getKnowledgeGraph).mockResolvedValue(graph);
  vi.mocked(api.previewLearningRoute).mockResolvedValue(preview);
  vi.mocked(api.saveLearningRoute).mockResolvedValue({route: saved});
  vi.mocked(api.getLearningRouteHistory).mockResolvedValue({items: [saved]});
});

test('route generation is explicit and saving binds the preview fingerprint', async () => {
  render(<LearningRoute {...props} route={null}/>);
  expect(screen.getByRole('combobox',{name:'路线学习目标'})).toBeVisible();
  expect(api.previewLearningRoute).not.toHaveBeenCalled();
  expect(api.saveLearningRoute).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole('button', {name: '预览学习路线'}));
  const region = await screen.findByRole('region', {name: '学习路线预览'});
  expect(within(region).getByText('向量点积')).toBeVisible();
  fireEvent.click(within(region).getByRole('button', {name: '保存并使用路线'}));
  await waitFor(() => expect(api.saveLearningRoute).toHaveBeenCalledWith('p', preview, 0));
  expect(props.onChanged).toHaveBeenCalledWith(saved);
});

test('step decisions and user reordering are persisted independently of self-assessment', async () => {
  vi.mocked(api.updateLearningRoute).mockResolvedValue({route: {...saved, revision: 2}});
  render(<LearningRoute {...props} route={saved}/>);
  const item = screen.getByRole('heading', {name: '向量点积'}).closest('li')!;
  fireEvent.click(within(item).getByRole('button', {name: '本次跳过'}));
  await waitFor(() => expect(api.updateLearningRoute).toHaveBeenLastCalledWith('p', {expected_revision: 1, step_node_id: 'dot', state: 'skipped'}));
  await screen.findByText('步骤已保存。学习自评保持由你单独确认。');
  fireEvent.click(screen.getByRole('button', {name: '下移：向量点积'}));
  await waitFor(() => expect(api.updateLearningRoute).toHaveBeenLastCalledWith('p', {expected_revision: 1, order: ['goal', 'dot']}));
  expect(screen.getByText(/完成步骤不等于已掌握知识/)).toBeVisible();
});

test('conflicting save retains the reviewed preview until explicit reread', async () => {
  vi.mocked(api.saveLearningRoute).mockRejectedValue(Object.assign(new Error('conflict'), {status: 409}));
  render(<LearningRoute {...props} route={saved}/>);
  fireEvent.click(screen.getByRole('button', {name: '重新规划此目标'}));
  fireEvent.click(await screen.findByRole('button', {name: '保存这次规划'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('你的选择仍保留');
  expect(screen.getByRole('region', {name: '学习路线预览'})).toBeVisible();
  expect(props.onChanged).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: '重新读取'}));
  expect(props.onReload).toHaveBeenCalledOnce();
  expect(screen.queryByRole('region', {name: '学习路线预览'})).not.toBeInTheDocument();
});

test('changed steps retain old evidence and require explicit current-context confirmation', async () => {
  const staleStep = {...saved.steps[0], stale: true, stale_reasons: ['教学资料：内容已变化'], current_context: 'new-fingerprint', current_evidence: [{...evidence, id: 'e2', quote: '当前版本：点积计算已修订。', source_version: 'v2'}]};
  const stale = {...saved, stale: true, steps: [staleStep, saved.steps[1]], next_node_id: null};
  vi.mocked(api.recheckLearningRoute).mockResolvedValue({route: {...saved, revision: 2}});
  render(<LearningRoute {...props} route={stale}/>);
  const item = screen.getByRole('heading', {name: '向量点积'}).closest('li')!;
  expect(within(item).getByRole('button', {name: '完成这一步'})).toBeDisabled();
  fireEvent.click(within(item).getByText('对照保存时与当前依据', {selector: 'summary'}));
  expect(within(item).getByText(evidence.quote)).toBeVisible();
  expect(within(item).getByText('当前版本：点积计算已修订。')).toBeVisible();
  fireEvent.click(within(item).getByRole('button', {name: '确认采用当前依据'}));
  await waitFor(() => expect(api.recheckLearningRoute).toHaveBeenCalledWith('p', 1, staleStep));
});

test('a late preview from a previous workspace cannot replace the new workspace state', async () => {
  let resolve!: (value: api.LearningRoutePreview) => void;
  vi.mocked(api.previewLearningRoute).mockImplementation(() => new Promise(r => {resolve = r;}));
  function Harness() {
    const [project, setProject] = useState('p');
    return <><button onClick={() => setProject('other')}>切换空间</button><LearningRoute {...props} projectId={project} route={null}/></>;
  }
  render(<Harness/>);
  fireEvent.click(await screen.findByRole('button', {name: '预览学习路线'}));
  fireEvent.click(screen.getByRole('button', {name: '切换空间'}));
  resolve(preview);
  await waitFor(() => expect(screen.queryByRole('region', {name: '学习路线预览'})).not.toBeInTheDocument());
  expect(api.saveLearningRoute).not.toHaveBeenCalled();
});

test('saved routes show steps first and keep a changed target when planning is collapsed',async()=>{
 render(<LearningRoute {...props} route={saved}/>);
 expect(screen.getByRole('heading',{name:'向量点积'})).toBeVisible();
 expect(screen.getByRole('button',{name:'继续：向量点积'})).toBeVisible();
 const target=screen.getByRole('combobox',{name:'路线学习目标',hidden:true});
 expect(target).not.toBeVisible();
 expect(api.previewLearningRoute).not.toHaveBeenCalled();
 const summary=screen.getByText('调整学习目标',{selector:'summary'});
 fireEvent.click(summary);
 expect(target).toBeVisible();
 await waitFor(()=>expect(target).toBeEnabled());
 fireEvent.mouseDown(target);
 fireEvent.click(await screen.findByText('向量点积',{selector:'.ant-select-item-option-content'}));
 fireEvent.click(summary);expect(target).not.toBeVisible();
 fireEvent.click(summary);expect(target).toBeVisible();
 expect(api.previewLearningRoute).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'预览学习路线'}));
 await waitFor(()=>expect(api.previewLearningRoute).toHaveBeenCalledWith('p','dot',expect.any(AbortSignal)));
});

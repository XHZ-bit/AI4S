import {useEffect, useRef, useState} from 'react';
import {Button} from 'antd';
import {notifyLearningRoute, updateLearningRoute, type SavedLearningRoute} from '../../api/knowledgeRoutes';
import {useCurrentAccount} from '../SessionContext';
import './learning-route.css';

export default function LearningRouteContinue({projectId, nodeId, route, loading, onChanged, onLearn, onRoute}: {
  projectId: string; nodeId?: string; route: SavedLearningRoute | null; loading: boolean;
  onChanged: (route: SavedLearningRoute) => void; onLearn: (id: string) => void; onRoute: () => void;
}) {
  const account = useCurrentAccount();
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const generation = useRef(0), inFlight = useRef(false);
  useEffect(() => {generation.current++; inFlight.current = false; setBusy(false); setMessage(''); setError(''); return () => {generation.current++;};}, [account?.id, projectId, nodeId]);
  const index = route?.steps.findIndex(step => step.node_id === nodeId) ?? -1;
  const step = route && index >= 0 ? route.steps[index] : undefined;
  if (!route || !step) return null;
  const needsReview = step.stale || !step.available || route.question_changed || route.needs_replan;
  const next = route.steps.find(item => item.node_id === route.next_node_id && item.node_id !== nodeId);
  async function finish() {
    if (!route || !step || busy || inFlight.current || loading || needsReview) return;
    const gen = generation.current; inFlight.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const value = await updateLearningRoute(projectId, {expected_revision: route.revision, step_node_id: step.node_id, state: 'done'});
      if (gen !== generation.current) return;
      onChanged(value.route); notifyLearningRoute(projectId);
      if (value.route.next_node_id && value.route.next_node_id !== nodeId) onLearn(value.route.next_node_id);
      else setMessage(value.route.stale || value.route.needs_replan ? '这一步已保存，后续路线需要复核。' : '这一步已保存，本次路线没有待进行的步骤。');
    } catch (e) {if (gen === generation.current) setError((e as {status?: number}).status === 409 ? '路线或依据已变化，当前阅读位置保留。请打开路线重新核对。' : '步骤未保存，请重试：' + String(e));}
    finally {if (gen === generation.current) {inFlight.current = false; setBusy(false);}}
  }
  return <aside className="kw-route-continue" aria-label="当前学习路线">
    <div><strong>{route.target_label} · 第 {index + 1} / {route.steps.length} 步</strong><p>{needsReview ? '目标或依据有变化，先核对路线。' : '完成记录只表示本次步骤已走过，理解程度由你单独自评。'}</p></div>
    <div className="kw-route-actions">
      {!needsReview && step.state === 'todo' && <Button type="primary" disabled={loading || busy} loading={busy} onClick={() => void finish()}>完成这一步并继续</Button>}
      {!needsReview && step.state !== 'todo' && next && <Button disabled={loading || busy} onClick={() => onLearn(next.node_id)}>继续下一步</Button>}
      <Button disabled={busy} onClick={onRoute}>{needsReview || error ? '核对学习路线' : '查看路线'}</Button>
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </aside>;
}

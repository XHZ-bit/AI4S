import {useEffect, useRef, useState} from 'react';
import {Button, Select, Spin} from 'antd';
import {ArrowDownOutlined, ArrowUpOutlined} from '@ant-design/icons';
import {getKnowledgeGraph, type KnowledgeEvidence, type KnowledgeNode} from '../../api/knowledge';
import {getLearningRouteHistory, notifyLearningRoute, previewLearningRoute, recheckLearningRoute, saveLearningRoute, updateLearningRoute,
  type LearningRoutePreview, type LearningRouteStep, type RouteStepState, type SavedLearningRoute} from '../../api/knowledgeRoutes';
import {useCurrentAccount} from '../SessionContext';
import './learning-route.css';
import MathText from '../learning/MathText';
import EvidenceQuote from './EvidenceQuote';

export const routeStateLabels: Record<RouteStepState, string> = {todo: '待进行', done: '已完成这一步', skipped: '本次跳过'};
interface Props {
  projectId: string;
  route: SavedLearningRoute | null;
  loading: boolean;
  loadError?: string;
  initialNode?: KnowledgeNode;
  onChanged: (route: SavedLearningRoute) => void;
  onReload: () => void;
  onLearn: (id: string) => void;
  onGraph: () => void;
  onEvidence: (evidence: KnowledgeEvidence) => void;
}
function errorMessage(error: unknown) {
  return (error as {status?: number})?.status === 409
    ? '路线、问题或依据已有变化。你的选择仍保留，请重新读取路线，并重新预览后保存。'
    : '操作未完成：' + (error instanceof Error ? error.message : String(error));
}
function Evidence({items, onOpen}: {items: KnowledgeEvidence[]; onOpen: Props['onEvidence']}) {
  return items.length ? <ul className="kw-route-evidence">{items.map(item => <li key={item.id}>
    <Button type="link" size="small" onClick={() => onOpen(item)}>{item.source_title || '原文依据'} · {item.locator?.page ? '第 ' + item.locator.page + ' 页' : item.locator?.heading || item.locator?.path || '原文片段'}</Button>
    <blockquote><EvidenceQuote evidence={item}/></blockquote>
  </li>)}</ul> : <p className="kw-route-muted">没有可定位的直接出处，不能据此判断原文。</p>;
}

export default function LearningRoute({projectId, route, loading, loadError, initialNode, onChanged, onReload, onLearn, onGraph, onEvidence}: Props) {
  const account = useCurrentAccount();
  const scope = `${account?.id || 'local'}:${projectId}`;
  const [target, setTarget] = useState<string>();
  const [query, setQuery] = useState('');
  const [nodes, setNodes] = useState<KnowledgeNode[]>([]);
  const [searchBusy, setSearchBusy] = useState(false), [searchError, setSearchError] = useState('');
  const [preview, setPreview] = useState<LearningRoutePreview>();
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [history, setHistory] = useState<SavedLearningRoute[]>(), [historyOpen, setHistoryOpen] = useState(false), [historyError, setHistoryError] = useState('');
  const generation = useRef(0), request = useRef<AbortController>();
  const changed = useRef(onChanged); changed.current = onChanged;
  useEffect(() => {
    generation.current++; request.current?.abort(); setPlannerOpen(false); setTarget(undefined); setQuery(''); setNodes([]); setPreview(undefined); setBusy(''); setError(''); setNotice(''); setHistory(undefined); setHistoryOpen(false); setHistoryError('');
    return () => {generation.current++; request.current?.abort();};
  }, [scope]);
  useEffect(() => {if (initialNode?.id) {setTarget(initialNode.id); setPreview(undefined);} }, [scope, initialNode?.id]);
  useEffect(() => {if (!target && route) setTarget(route.target_node_id);}, [target, route?.target_node_id]);
  useEffect(() => {
    const controller = new AbortController(); setSearchBusy(true); setSearchError('');
    const timer = window.setTimeout(() => {
      getKnowledgeGraph(projectId, {q: query || undefined, limit: 80, overview: false}, controller.signal)
        .then(value => {if (!controller.signal.aborted) setNodes(value.nodes.filter(node => !node.hidden && !node.metadata?.structural && !['paper', 'report', 'code', 'results', 'resource'].includes(node.kind)));})
        .catch(e => {if (!controller.signal.aborted) setSearchError('知识列表未读到，可重开页面重试：' + String(e));})
        .finally(() => {if (!controller.signal.aborted) setSearchBusy(false);});
    }, query ? 250 : 0);
    return () => {controller.abort(); window.clearTimeout(timer);};
  }, [scope, projectId, query]);
  useEffect(() => {
    if (!historyOpen) return;
    const controller = new AbortController(); setHistoryError('');
    getLearningRouteHistory(projectId, controller.signal).then(value => {if (!controller.signal.aborted) setHistory(value.items);})
      .catch(e => {if (!controller.signal.aborted) setHistoryError('历史暂未读取：' + String(e));});
    return () => controller.abort();
  }, [historyOpen, projectId, scope, route?.revision]);
  const options = [...new Map([
    ...(initialNode ? [{value: initialNode.id, label: initialNode.label}] : []),
    ...(route ? [{value: route.target_node_id, label: route.target_label}] : []),
    ...nodes.map(node => ({value: node.id, label: node.label})),
  ].map(item => [item.value, item])).values()];
  async function prepare(id = target) {
    if (!id || busy || loading) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const gen = generation.current; setTarget(id); setBusy('preview'); setError(''); setNotice('');
    try {const value = await previewLearningRoute(projectId, id, controller.signal); if (gen === generation.current && !controller.signal.aborted) setPreview(value);}
    catch (e) {if (gen === generation.current && !controller.signal.aborted) setError(errorMessage(e));}
    finally {if (gen === generation.current && !controller.signal.aborted) setBusy('');}
  }
  async function mutate(key: string, operation: () => Promise<{route: SavedLearningRoute}>, message: string) {
    if (busy || loading) return;
    const gen = generation.current; setBusy(key); setError(''); setNotice('');
    try {
      const value = await operation(); if (gen !== generation.current) return;
      changed.current(value.route); if(key==='save')setPlannerOpen(false); setPreview(undefined); setHistory(undefined); setNotice(message); notifyLearningRoute(projectId);
    } catch (e) {if (gen === generation.current) setError(errorMessage(e));}
    finally {if (gen === generation.current) setBusy('');}
  }
  function state(step: LearningRouteStep, next: RouteStepState) {
    if (route) void mutate(step.node_id, () => updateLearningRoute(projectId, {expected_revision: route.revision, step_node_id: step.node_id, state: next}), '步骤已保存。学习自评保持由你单独确认。');
  }
  function move(index: number, direction: number) {
    if (!route) return;
    const order = route.steps.map(step => step.node_id); const destination = index + direction;
    if (destination < 0 || destination >= order.length) return;
    [order[index], order[destination]] = [order[destination], order[index]];
    void mutate('order', () => updateLearningRoute(projectId, {expected_revision: route.revision, order}), '顺序已保存。调整顺序不会建立新的知识关系。');
  }
  const disabled = !!busy || loading || !!loadError;
  const next = route?.steps.find(step => step.node_id === route.next_node_id);
  const completed = route?.steps.filter(step => step.state === 'done').length || 0;
  const builder=<>
    <div className="kw-route-builder"><label>这次想理解的目标<Select aria-label="路线学习目标" value={target} placeholder="选择知识，或搜索标题" showSearch filterOption={false} onSearch={setQuery} loading={searchBusy} disabled={disabled} options={options} onChange={id => {setTarget(id); setPreview(undefined); setNotice('');}}/></label>
      <Button disabled={disabled || !target || !!loadError} loading={busy === 'preview'} onClick={() => void prepare()}>预览学习路线</Button></div>
    {searchError && <p role="alert">{searchError}</p>}
  </>;
  return <section className="kw-learning-route" aria-label="我的学习路线">
    <header className="kw-route-heading"><div><h2>我的学习路线</h2></div><Button disabled={!!busy || loading} onClick={() => {setPreview(undefined); setError(''); onReload();}}>重新读取</Button></header>
    {loading && <div role="status"><Spin size="small"/> 读取已保存路线…</div>}
    {loadError && <p role="alert">路线暂未读取：{loadError}。可以重新读取，其他学习入口仍可使用。</p>}
    {route&&<>
      <section className="kw-route-current" aria-label="已保存的学习路线"><div><h3 title={route.target_label}>{route.target_label}</h3><p>{route.research_question || '按目标节点组织的学习路线'}</p><small>已完成 {completed} / {route.steps.length} 步 · 路线修订 {route.revision}。完成步骤不等于已掌握知识。</small></div>
        <div className="kw-route-actions">{next && <Button type="primary" disabled={disabled} onClick={() => onLearn(next.node_id)}>继续：{next.label}</Button>}<Button disabled={disabled} onClick={onGraph}>在图谱中查看路线</Button><Button disabled={disabled} onClick={() => void prepare(route.target_node_id)}>重新规划此目标</Button></div>
      </section>
    </>}
    {route?<details className="kw-route-planner" open={plannerOpen} onToggle={event=>{if(event.target===event.currentTarget)setPlannerOpen(event.currentTarget.open)}}><summary>调整学习目标</summary>{builder}</details>:<section className="kw-route-planner is-initial" aria-label="规划学习路线">{builder}</section>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {preview && <section className="kw-route-preview" aria-label="学习路线预览"><h3>通向{preview.target_label}</h3>
      <p>依据当前有效的先修关系整理。下列步骤的排列不代表相邻知识之间一定有直接连线。</p>
      {!!preview.warnings.length && <ul className="kw-route-warnings">{preview.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
      <ol>{preview.steps.map(step => <li key={step.node_id}><strong>{step.label}</strong><span>{step.role === 'target' ? '学习目标' : '已有先修关系'}{step.state !== 'todo' ? ' · ' + routeStateLabels[step.state] : ''}</span></li>)}</ol>
      <p className="kw-route-muted">教学补充可以就地阅读，不会被当作必须完成的先修关卡。重新规划同一目标会保留有效步骤的个人决定。</p>
      <div className="kw-route-actions"><Button type="primary" disabled={disabled} loading={busy === 'save'} onClick={() => void mutate('save', () => saveLearningRoute(projectId, preview, route?.revision || 0), '学习路线已保存，下次可以直接继续。')}>{route ? '保存这次规划' : '保存并使用路线'}</Button><Button disabled={disabled} onClick={() => setPreview(undefined)}>收起预览</Button></div>
    </section>}
    {!route && !loading && !loadError && !preview && <p className="kw-route-empty">还没有保存路线。选择一个目标，先看看已有知识能提供哪些学习起点。</p>}
    {route && <>
      {route.question_changed && <p role="note" className="kw-route-warning">空间问题已有变化，当前保留保存时的问题。请检查这条路线是否仍适合，再重新规划。</p>}
      {!!route.warnings.length && <ul className="kw-route-warnings">{route.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
      {!next && <p role="status">{route.needs_replan ? '发现尚未加入的前置知识，请重新规划。逐项复核会保留旧路线，不会自动增加步骤。' : route.steps.some(step => step.stale) ? '有步骤需要复核。旧记录仍保留，可展开对照当前依据。' : '本次路线没有待进行的步骤，可以重开任意一步或选择新目标。'}</p>}
      <ol className="kw-route-steps">{route.steps.map((step, index) => <li key={step.node_id} className={step.node_id === route.next_node_id ? 'is-next' : undefined}>
        <div className="kw-route-step-heading"><div><h4>{step.label}</h4><div className="kw-route-step-meta"><span>{step.role === 'target' ? '学习目标' : '先修知识'}</span><span>{routeStateLabels[step.state]}</span>{step.node_id === route.next_node_id && <strong>下一步</strong>}{step.stale && <strong>需要复核</strong>}</div></div>
          <div className="kw-route-step-order"><Button size="small" aria-label={'上移：' + step.label} icon={<ArrowUpOutlined/>} disabled={disabled || index === 0} onClick={() => move(index, -1)}/><Button size="small" aria-label={'下移：' + step.label} icon={<ArrowDownOutlined/>} disabled={disabled || index === route.steps.length - 1} onClick={() => move(index, 1)}/></div></div>
        {!!step.stale_reasons.length && <ul className="kw-route-warnings">{step.stale_reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
        {!!step.warnings?.length && <ul className="kw-route-warnings">{step.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
        {!!step.blocked_by?.length && <p className="kw-route-warning">有相关前置步骤需要复核，或尚未加入路线；请先检查路线说明，仍可手动打开当前知识。</p>}
        <div className="kw-route-actions"><Button disabled={disabled || !step.available} onClick={() => onLearn(step.node_id)}>打开这一步</Button>{step.state !== 'done' && <Button disabled={disabled || step.stale || !step.available} onClick={() => state(step, 'done')}>完成这一步</Button>}{step.state !== 'skipped' && <Button type="text" disabled={disabled} onClick={() => state(step, 'skipped')}>本次跳过</Button>}{step.state !== 'todo' && <Button type="text" disabled={disabled} onClick={() => state(step, 'todo')}>重新进行</Button>}</div>
        <details className="kw-route-step-context"><summary>{step.stale ? '对照保存时与当前依据' : '为什么在这条路线中'}</summary>
          <p>{step.role === 'target' ? '这是你选择的学习目标。' : '根据已保存的真实先修关系进入本次路线。用户排序只安排学习步骤。'}</p>
          <div className={step.stale ? 'kw-route-context-columns' : undefined}><section><h5>保存时的内容</h5><p><MathText text={step.snapshot.node.summary} showSourceOnError/></p><small>{step.snapshot.source?.title} · {step.snapshot.source?.version || (step.snapshot.node.metadata?.educational ? '教学补充' : '未绑定来源')}</small><Evidence items={step.snapshot.evidence || []} onOpen={onEvidence}/>
            {!!step.snapshot.prerequisites?.length && <ul>{step.snapshot.prerequisites.map(edge => <li key={edge.id}>{edge.label || '先修关系'}{edge.explanation&&<> · <MathText text={edge.explanation}/></>}</li>)}</ul>}</section>
            {step.stale && <section><h5>当前内容</h5><p><MathText text={step.current_node?.summary || '当前知识或来源不可用，旧记录仍可阅读。'} showSourceOnError/></p><small>{step.current_source?.title} · {step.current_source?.version}</small><Evidence items={step.current_evidence || []} onOpen={onEvidence}/>{step.available && step.current_context && <Button disabled={disabled} onClick={() => void mutate('recheck', () => recheckLearningRoute(projectId, route.revision, step), '当前依据已确认，先前修订保留在历史中。')}>确认采用当前依据</Button>}</section>}
          </div>
        </details>
      </li>)}</ol>
      <details className="kw-route-history" open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}><summary>路线修订历史</summary>
        {historyError && <p role="alert">{historyError}</p>}{!history && !historyError && <p>读取历史…</p>}
        {history?.map(item => <details key={item.revision}><summary>修订 {item.revision} · {item.target_label} · {item.updated_at}</summary><p>{item.research_question}</p><ol>{item.steps.map(step => <li key={step.node_id}>{step.label} · {routeStateLabels[step.state]}</li>)}</ol></details>)}
      </details>
    </>}
    <details className="kw-route-help"><summary>路线说明</summary><p>围绕一个目标安排这次学习。步骤可以调整，所有知识都能随时打开。</p></details>
  </section>;
}

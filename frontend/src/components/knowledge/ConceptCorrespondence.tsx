import {useEffect, useRef, useState} from 'react';
import {Button} from 'antd';
import type {KnowledgeEvidence, KnowledgeNode} from '../../api/knowledge';
import {createConceptCorrespondence, getConceptCorrespondences, reviseConceptCorrespondence,
  type ConceptCollection, type ConceptCorrespondence as Correspondence, type ConceptDecision, type ConceptSide} from '../../api/knowledgeConcepts';
import {EvidenceList} from './KnowledgeSources';
import MathText from '../learning/MathText';
import {useCurrentAccount} from '../SessionContext';
import './concept-correspondence.css';

const labels: Record<ConceptDecision, string> = {
  comparable: '可对照', conditions_differ: '条件有差异', uncertain: '暂无法确定', rejected: '驳回这个对应',
};

function Side({side, onEvidence, onNode}: {side: ConceptSide; onEvidence: (value: KnowledgeEvidence) => void; onNode: (node: KnowledgeNode) => void}) {
  return <article className="kw-concept-side">
    <h4>{side.node.label}</h4>
    <p className="kw-concept-source">{side.source_title} · 节点版本 {side.node.version}</p>
    <MathText text={side.node.summary || '当前节点尚无独立定义，请结合原文核对。'}/>
    {Object.keys(side.conditions).length > 0 && <details><summary>定义涉及的条件</summary><dl>{Object.entries(side.conditions).map(([key, value]) =>
      <div key={key}><dt>{{conditions:'条件', assumptions:'假设', inputs:'输入', outputs:'输出', units:'单位'}[key] || key}</dt><dd>{typeof value === 'string' ? <MathText text={value} showSourceOnError/> : JSON.stringify(value)}</dd></div>)}</dl></details>}
    <EvidenceList items={side.evidence} onOpen={onEvidence}/>
    {!side.evidence.length && <p>缺少当前可定位的原文依据，可先保存为暂无法确定。</p>}
    <Button size="small" type="text" onClick={() => onNode(side.node)}>查看这个节点</Button>
  </article>;
}

export default function ConceptCorrespondence({projectId, nodeId, onEvidence, onNode, onSaved, onCompare}: {
  projectId: string; nodeId: string; onEvidence: (value: KnowledgeEvidence) => void;
  onNode: (node: KnowledgeNode) => void; onSaved?: () => void; onCompare?: () => void;
}) {
  const account = useCurrentAccount();
  const draftKey = `paperstride:${account?.id || 'local'}:concept-draft:${projectId}:${nodeId}`;
  const [open, setOpen] = useState(false), [data, setData] = useState<ConceptCollection>();
  const [search, setSearch] = useState(''), [query, setQuery] = useState(''), [source, setSource] = useState('');
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [retry, setRetry] = useState(0);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [target, setTarget] = useState<ConceptSide>(), [record, setRecord] = useState<Correspondence>();
  const [status, setStatus] = useState<ConceptDecision>('uncertain'), [explanation, setExplanation] = useState('');
  const generation = useRef(0);
  const restoringRecord = useRef('');
  const [draftScope, setDraftScope] = useState('');
  useEffect(() => {
    generation.current++; setOpen(false); setData(undefined); setTarget(undefined); setRecord(undefined);
    setError(''); setNotice(''); setBusy(false); setSearch(''); setQuery(''); setSource('');
    restoringRecord.current = '';
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey) || 'null');
      if (draft?.projectId === projectId && draft?.nodeId === nodeId) {
        setOpen(draft.open === true);
        setSearch(typeof draft.search === 'string' ? draft.search : '');
        setQuery(typeof draft.query === 'string' ? draft.query : '');
        setSource(typeof draft.source === 'string' ? draft.source : '');
        setExplanation(typeof draft.explanation === 'string' ? draft.explanation : '');
        if (Object.keys(labels).includes(draft.status)) setStatus(draft.status);
        if (draft.target?.node?.id && typeof draft.target.source_id === 'string') setTarget(draft.target);
        restoringRecord.current = typeof draft.recordId === 'string' ? draft.recordId : '';
      }
    } catch { /* Invalid browser drafts do not affect server records. */ }
    setDraftScope(draftKey);
    return () => { generation.current++; };
  }, [projectId, nodeId, draftKey]);
  useEffect(() => {
    if (draftScope !== draftKey) return;
    try {
      localStorage.setItem(draftKey, JSON.stringify({projectId, nodeId, open, search, query, source,
        status, explanation, target, recordId:record?.id || restoringRecord.current}));
    } catch { /* Current inputs remain editable when browser storage is unavailable. */ }
  }, [draftScope, draftKey, projectId, nodeId, open, search, query, source, status, explanation, target, record]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setLoading(true); setError('');
    getConceptCorrespondences(projectId, nodeId, query, source || undefined, controller.signal)
      .then(value => {
        if (controller.signal.aborted) return;
        setData(value);
        const saved = value.items.find(item => item.id === restoringRecord.current);
        if (saved) { setRecord(saved); setTarget(saved.current_right || saved.right); }
        restoringRecord.current = '';
      })
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, nodeId, open, query, source, retry]);

  function choose(side: ConceptSide) {
    const saved = data?.items.find(item => item.right.node.id === side.node.id);
    setTarget(side); setRecord(saved); setStatus(saved?.status || 'uncertain');
    setExplanation(saved?.explanation || ''); setNotice('');
  }
  function edit(value: Correspondence) {
    setRecord(value); setTarget(value.current_right || value.right); setStatus(value.status);
    setExplanation(value.explanation); setNotice('');
  }
  const left = record?.current_left || data?.node;
  const right = target;
  const canConfirm = left?.available && right?.available && !!left.evidence.length && !!right.evidence.length;
  async function save() {
    if (!left || !right || busy) return;
    const token = generation.current; setBusy(true); setError(''); setNotice('');
    const body = {status, explanation, left_node_version:left.node.version, right_node_version:right.node.version,
      left_source_version:left.source_version, right_source_version:right.source_version,
      left_evidence_fingerprint:left.evidence_fingerprint, right_evidence_fingerprint:right.evidence_fingerprint};
    try {
      const saved = await (record ? reviseConceptCorrespondence(projectId, nodeId, record.id, {...body, expected_revision:record.revision})
        : createConceptCorrespondence(projectId, nodeId, {...body, other_node_id:right.node.id}));
      if (token !== generation.current) return;
      setRecord(saved); setTarget(saved.current_right || saved.right);
      setData(old => old ? {...old, items:[saved, ...old.items.filter(item => item.id !== saved.id)],
        candidates:old.candidates.filter(item => item.side.node.id !== saved.right.node.id)} : old);
      setNotice('个人判断已保存，包含双方定义、原文位置及版本'); onSaved?.();
    } catch (cause) { if (token === generation.current) setError(String(cause)); }
    finally { if (token === generation.current) setBusy(false); }
  }

  return <details className="kw-concept-correspondence" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>核对跨论文概念</summary>
    {open && <>
      <p>从当前空间的全部有效知识中寻找候选，逐侧核对定义和适用条件。候选按本地词项与双语术语匹配，人工决定会保留。</p>
      <div className="kw-concept-search"><label>查找其他概念<input type="search" value={search} maxLength={300} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); setQuery(search.trim()); setRetry(value => value + 1); } }}/></label>
        <Button disabled={loading} onClick={() => { setQuery(search.trim()); setRetry(value => value + 1); }}>查找概念</Button>
        <label>资料范围<select value={source} onChange={event => setSource(event.target.value)}><option value="">其他全部资料</option>{data?.sources.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label></div>
      {loading && <p role="status">读取当前空间的概念与依据…</p>}
      {error && <div role="alert">{error}<Button type="link" onClick={() => setRetry(value => value + 1)}>重新读取双方依据</Button></div>}
      {data && <>
        {data.candidates.length > 0 && <ul className="kw-concept-candidates">{data.candidates.map(candidate => <li key={candidate.side.node.id}>
          <div><strong>{candidate.side.node.label}</strong><small>{candidate.side.source_title} · {candidate.reason}</small></div>
          <Button size="small" onClick={() => choose(candidate.side)}>核对这两个概念</Button>
        </li>)}</ul>}
        {!data.candidates.length && !loading && <p>当前没有尚未核对的匹配候选，可以搜索名称或从其他资料手工选择。</p>}
        <label className="kw-concept-manual">手工选择另一节点<select aria-label="手工选择对照概念" value={target?.node.id || ''} onChange={event => {
          const found = data.choices.find(item => item.node.id === event.target.value); if (found) choose(found);
        }}><option value="">选择其他资料里的节点</option>{target && !data.choices.some(item => item.node.id === target.node.id) && <option value={target.node.id}>{target.node.label}</option>}
          {data.choices.map(item => <option key={item.node.id} value={item.node.id}>{item.source_title} · {item.node.label}</option>)}</select></label>
        {data.truncated && <p>当前展示前40个匹配节点，可以输入更具体的名称或限定资料。</p>}
        {left && right && <section className="kw-concept-review" aria-label="概念双侧核对">
          <div className="kw-concept-sides"><Side side={left} onEvidence={onEvidence} onNode={onNode}/><Side side={right} onEvidence={onEvidence} onNode={onNode}/></div>
          {record?.stale && <div role="note">保存时的依据已有变化 · {record.stale_reasons.join('、')}<details><summary>查看原判断及版本快照</summary><p><MathText text={record.explanation} showSourceOnError/></p><div className="kw-concept-sides"><Side side={record.left} onEvidence={onEvidence} onNode={onNode}/><Side side={record.right} onEvidence={onEvidence} onNode={onNode}/></div></details></div>}
          <label>我的核对结果<select aria-label="概念核对结果" value={status} onChange={event => setStatus(event.target.value as ConceptDecision)} disabled={busy}>{Object.entries(labels).map(([value, label]) =>
            <option key={value} value={value} disabled={!canConfirm && ['comparable', 'conditions_differ'].includes(value)}>{label}</option>)}</select></label>
          <label>我的判断依据<textarea aria-label="概念核对说明" value={explanation} maxLength={3500} rows={3} onChange={event => setExplanation(event.target.value)} disabled={busy}/></label>
          <p>可对照或条件差异会作为用户判断进入图谱。原文事实和自己的解释可继续分别核查。</p>
          <Button type="primary" aria-label="保存概念核对" loading={busy} disabled={loading || busy || (!canConfirm && ['comparable', 'conditions_differ'].includes(status))} onClick={() => void save()}>保存我的判断</Button>
          {onCompare && <Button type="text" onClick={onCompare}>打开资料比较</Button>}
          <p role="status">{notice}</p>
        </section>}
        {data.items.length > 0 && <section><h4>已保存的概念判断</h4><ul className="kw-concept-decisions">{data.items.map(item => <li key={item.id}>
          <Button type="link" onClick={() => edit(item)}>{item.right.node.label} · {labels[item.status]}</Button>
          <small>{item.reviewed_by} · 修订 {item.revision}{item.stale ? ' · 依据变化待复核' : ''}</small>
        </li>)}</ul></section>}
      </>}
    </>}
  </details>;
}

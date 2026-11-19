import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Input, Select, Space, Spin} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import {getSourceCoverage, reviewSourceCoverage, supplementSourceCoverage, type CoverageCategory, type CoverageDecisionStatus, type SourceCoverageData} from '../../api/knowledgeCoverage';
import './source-coverage.css';

const stateLabels = {
  covered: '已有原文依据', missing: '待补充核对', not_extracted: '尚无已抽取内容',
  not_reported: '用户标记未报告', not_applicable: '用户标记不适用',
};

export default function SourceCoverage({projectId, sourceId, sourceVersion, analysisVersion, onRead, onGraph, onEvidence, onUpdated}: {
  projectId: string; sourceId: string; sourceVersion: string; analysisVersion?: string;
  onRead: (id: string) => void; onGraph: (id: string) => void;
  onEvidence?: (evidence: KnowledgeEvidence) => void; onUpdated: () => void;
}) {
  const [open, setOpen] = useState(false), [data, setData] = useState<SourceCoverageData>();
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState('');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [retry, setRetry] = useState(0);
  const [review, setReview] = useState<{category: CoverageCategory; reason: string; status: CoverageDecisionStatus}>();
  const generation = useRef(0), readSequence = useRef(0), inFlight = useRef(false);
  useEffect(() => {
    generation.current++; setData(undefined); setReview(undefined); setBusy(''); inFlight.current = false;
    return () => { generation.current++; };
  }, [projectId, sourceId]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(), sequence = ++readSequence.current; setLoading(true); setError('');
    getSourceCoverage(projectId, sourceId, controller.signal).then(result => {
      if (!controller.signal.aborted && sequence === readSequence.current) setData(result);
    }).catch(cause => { if (!controller.signal.aborted && sequence === readSequence.current) setError(String(cause)); })
      .finally(() => { if (!controller.signal.aborted && sequence === readSequence.current) setLoading(false); });
    return () => controller.abort();
  }, [open, projectId, sourceId, sourceVersion, analysisVersion, retry]);

  async function act(category: CoverageCategory, action: 'supplement' | CoverageDecisionStatus) {
    if (!data || inFlight.current) return;
    const token = generation.current; inFlight.current = true; readSequence.current++; setLoading(false); setBusy(category); setError(''); setNotice('');
    const expected = {category, expected_source_version: data.source_version, expected_revision: data.revision};
    try {
      const result = action === 'supplement' ? await supplementSourceCoverage(projectId, sourceId, expected)
        : await reviewSourceCoverage(projectId, sourceId, {...expected, status: action, reason: review?.reason || ''});
      if (token !== generation.current) return;
      readSequence.current++; setLoading(false); setData(result); setReview(undefined); setNotice(result.notice || '覆盖判断已保存，可随时重新核对。'); onUpdated();
    } catch (cause) { if (token === generation.current) setError(String(cause)); }
    finally { if (token === generation.current) { inFlight.current = false; setBusy(''); } }
  }

  return <details className="kw-source-coverage" open={open} onToggle={event => {
    if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
  }}><summary>检查内容覆盖与缺项</summary>
    {open && <div className="kw-source-coverage-body">
      {loading && <div role="status"><Spin size="small"/> 正在读取已保存的知识…</div>}
      {error && <Alert type="warning" message="覆盖记录读取或操作未完成" description={error}
        action={<Button disabled={!!busy} onClick={() => setRetry(value => value + 1)}>重新读取</Button>}/>}
      {notice && <p role="status">{notice}</p>}
      {data && <>
        <p className="kw-coverage-scope">{data.scope}</p>
        {!data.parsed && <p>文本结构仍在准备，可先阅读原文件，完成解析后再补充知识。</p>}
        {data.analysis_running && <p role="status">这份资料正在分析。现有内容仍可阅读，完成后可针对缺项补充。</p>}
        <ul className="kw-coverage-items">{data.items.map(item => <li key={item.category}>
          <div className="kw-coverage-item-heading"><strong>{item.label}</strong><span>{stateLabels[item.state]}</span>
            {item.node_count > 0 && <small>{item.node_count} 个知识点 · {item.evidence_count} 处依据</small>}</div>
          {!!item.nodes.length && <p className="kw-coverage-node-labels">{item.nodes.map(node => node.label).join('、')}</p>}
          {item.decision && <p className="kw-coverage-decision">{item.decision.reason} · {item.decision.reviewed_by}
            {item.decision_stale && <span role="note"> 原文或已抽取内容已有变化，请重新核对这项判断。</span>}</p>}
          {!!item.evidence.length && <details className="kw-coverage-evidence"><summary>查看本项原文依据</summary>
            <ul>{item.evidence.map(evidence => <li key={evidence.id}><Button type="link" onClick={() => onEvidence ? onEvidence(evidence) : onRead(sourceId)}>
              {evidence.locator.page ? '第 ' + evidence.locator.page + ' 页' : evidence.locator.heading || '原文片段'}</Button>
              <p>{evidence.quote.slice(0, 260)}</p></li>)}</ul></details>}
          <Space wrap>
            {item.node_count === 0 && <Button size="small" disabled={!!busy || !data.parsed || !data.model_available || data.analysis_running}
              loading={busy === item.category} onClick={() => void act(item.category, 'supplement')}>补充分析{item.label}</Button>}
            {item.node_count === 0 && <Button type="text" size="small" disabled={!!busy}
              onClick={() => setReview({category: item.category, reason: item.decision?.reason || '', status: item.decision?.status === 'not_applicable' ? 'not_applicable' : 'not_reported'})}>记录我的判断</Button>}
            {item.decision && <Button type="text" size="small" disabled={!!busy} onClick={() => void act(item.category, 'reset')}>恢复待核对</Button>}
          </Space>
          {review?.category === item.category && <div className="kw-coverage-review">
            <label>这项内容在原文中的情况<Select aria-label={'覆盖判断类型：' + item.label} value={review.status}
              disabled={!!busy} onChange={status => setReview({...review, status})}
              options={[{value:'not_reported', label:'原文未报告'}, {value:'not_applicable', label:'本资料不适用'}]}/></label>
            <label>我的判断理由<Input.TextArea aria-label={'覆盖判断理由：' + item.label} value={review.reason} maxLength={1500}
              autoSize={{minRows:2, maxRows:5}} disabled={!!busy} onChange={event => setReview({...review, reason: event.target.value})}/></label>
            <Space><Button size="small" type="primary" disabled={!review.reason.trim() || !!busy}
              onClick={() => void act(item.category, review.status)}>保存判断</Button><Button size="small" disabled={!!busy} onClick={() => setReview(undefined)}>取消</Button></Space>
          </div>}
        </li>)}</ul>
        <p className="kw-coverage-scope">补充分析由你点击后请求模型，每次只处理所选类型的有限原文片段。{!data.model_available && '当前模型未启用，可先阅读或记录人工判断。'}</p>
        <Space><Button size="small" onClick={() => onRead(sourceId)}>阅读这份原文</Button><Button size="small" onClick={() => onGraph(sourceId)}>查看资料图谱</Button></Space>
      </>}
    </div>}
  </details>;
}

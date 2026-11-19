import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Input, Space, Spin} from 'antd';
import {answerNodeCheck, dismissNodeCheck, getNodeChecks, type CheckAttempt, type NodeChecks} from '../../api/knowledgeChecks';
import './learning-check.css';
import MathText from '../learning/MathText';

export default function LearningCheck({projectId, nodeId}: {projectId: string; nodeId: string}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<NodeChecks>();
  const [selected, setSelected] = useState('');
  const [answer, setAnswer] = useState('');
  const [explanation, setExplanation] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<CheckAttempt>();
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const lastContext = useRef('');
  useEffect(() => {
    generation.current++; lastContext.current=''; setData(undefined); setOpen(false); setSelected(''); setAnswer('');
    setExplanation(''); setResult(undefined); setBusy(false); setError('');
    return () => { generation.current++; };
  }, [projectId, nodeId]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setLoading(true); setError('');
    getNodeChecks(projectId, nodeId, controller.signal).then(value => {
      if (!controller.signal.aborted) {
        if(lastContext.current!==value.context_fingerprint){setAnswer('');lastContext.current=value.context_fingerprint;}
        setData(value); setSelected(old => value.questions.some(item => item.id === old) ? old : value.questions[0]?.id || '');
        setResult(old => old ? value.history.find(item => item.id === old.id) : undefined);
      }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, projectId, nodeId, retry]);
  const question = data?.questions.find(item => item.id === selected);
  async function submit() {
    if (!data || !question || !answer || busy) return;
    const token = generation.current; setBusy(true); setError('');
    try {
      const value = await answerNodeCheck(projectId, nodeId, question.id, {answer_id: answer, expected_context: data.context_fingerprint, explanation});
      if (token !== generation.current) return;
      setResult(value); setData(old => old ? {...old, history: [value, ...old.history]} : old);
      window.dispatchEvent(new CustomEvent('paperstride:learning-check', {detail: {projectId, nodeId}}));
    } catch (cause) { if (token === generation.current) setError(String(cause)); }
    finally { if (token === generation.current) setBusy(false); }
  }
  async function dismiss(attempt: CheckAttempt) {
    const token = generation.current; setBusy(true); setError('');
    try {
      await dismissNodeCheck(projectId, nodeId, attempt.id);
      if (token !== generation.current) return;
      setResult(old => old?.id === attempt.id ? {...old, dismissed: true} : old);
      setData(old => old ? {...old, history: old.history.map(item => item.id === attempt.id ? {...item, dismissed: true} : item)} : old);
      window.dispatchEvent(new CustomEvent('paperstride:learning-check', {detail: {projectId, nodeId}}));
    } catch (cause) { if (token === generation.current) setError(String(cause)); }
    finally { if (token === generation.current) setBusy(false); }
  }
  return <details className="kw-learning-check" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>用一个问题检验理解</summary>
    {open && <>
      <p>自编教学题，根据本题回答推荐下一步。你可以跳过，也可以保留不同解释。</p>
      {loading && <Spin size="small"/>}
      {error && <Alert type="warning" message="教学检查暂未完成" description={error} action={<Button onClick={() => setRetry(value => value + 1)}>重新读取题目</Button>}/>}
      {data && !data.questions.length && <p>当前知识点暂无固定教学题，可以在下方围绕原文提问。</p>}
      {question && <>
        {data!.questions.length > 1 && <label className="kw-check-select">选择本次问题<select aria-label="选择教学检查" value={selected} disabled={busy} onChange={event => {setSelected(event.target.value); setAnswer(''); setExplanation(''); setResult(undefined);}}>{data!.questions.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}
        <fieldset disabled={busy || loading || !data!.available}><legend><MathText text={question.question}/></legend>
          {question.choices.map(choice => <label key={choice.id}><input type="radio" name={`check-${nodeId}`} value={choice.id} checked={answer === choice.id} onChange={() => {setAnswer(choice.id); setResult(undefined);}}/><MathText text={choice.text}/></label>)}
          <label className="kw-check-explanation">我的理由（可选）<Input.TextArea aria-label="教学检查我的理由" value={explanation} maxLength={4000} autoSize={{minRows:2,maxRows:5}} onChange={event => setExplanation(event.target.value)}/></label>
        </fieldset>
        {!data!.available && <p>当前来源或知识点需复核，历史回答仍可查看。</p>}
        <Space><Button type="primary" aria-label="保存回答并看建议" loading={busy} disabled={!answer || loading || !data!.available} onClick={() => void submit()}>保存回答并看建议</Button><Button onClick={() => setOpen(false)}>先跳过</Button></Space>
      </>}
      {result && <div className="kw-check-feedback" role="status"><strong>{result.correct ? '本题回答符合教学条件' : '可以从这里继续理解'}</strong><p><MathText text={result.feedback} showSourceOnError/></p>{result.stale&&<small>知识或依据已变化，保留当时的回答。</small>}{result.dismissed ? <small>已记录你的反馈，下一步建议将跳过这条记录。</small> : <Button type="text" disabled={busy} onClick={() => void dismiss(result)}>这条建议不适合我</Button>}</div>}
      {!!data?.history.length && <details className="kw-check-history"><summary>我的回答记录 · {data.history.length}</summary><ul>{data.history.map(item => <li key={item.id}><strong><MathText text={item.question}/></strong><p>我的回答 · <MathText text={item.answer}/></p>{item.explanation && <p>我的理由 · <MathText text={item.explanation} showSourceOnError/></p>}<p><MathText text={item.feedback} showSourceOnError/></p>{item.stale && <small>知识或依据已变化，保留当时的回答。</small>}{item.dismissed ? <small>已反馈建议不适合。</small> : !item.correct&&<Button type="text" disabled={busy} onClick={()=>void dismiss(item)}>不再根据这条回答推荐</Button>}</li>)}</ul></details>}
    </>}
  </details>;
}

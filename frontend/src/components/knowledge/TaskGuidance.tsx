import {useEffect, useMemo, useState} from 'react';
import {Button} from 'antd';
import type {KnowledgeGraph, KnowledgeNode, KnowledgeSource} from '../../api/knowledge';
import {getLearningProgress, getNodeSummary, type NodeProgress} from '../../api/knowledgeExperience';
import {resumeDescription, type WorkspaceResume} from './workspaceResume';
import {getCheckRecommendation,type CheckRecommendation} from '../../api/knowledgeChecks';
import type {SavedLearningRoute} from '../../api/knowledgeRoutes';
import './task-guidance.css';

interface Props {
  projectId: string;
  question: string;
  graph?: KnowledgeGraph;
  sources: KnowledgeSource[];
  resume?: WorkspaceResume;
  onResume: (url: string) => void;
  onLearn: (id: string) => void;
  onRead: (id: string) => void;
  onImport: () => void;
  learningRoute?: SavedLearningRoute | null;
  onRoute?: () => void;
}

export default function TaskGuidance({projectId, question, graph, sources, resume, onResume, onLearn, onRead, onImport, learningRoute, onRoute}: Props) {
  const [progress, setProgress] = useState<NodeProgress[]>([]);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [foundation, setFoundation] = useState<{id: string; label: string}>();
  const [progressError, setProgressError] = useState(false);
  const [personalAdvice,setPersonalAdvice]=useState<CheckRecommendation|null>(null);
  useEffect(()=>{
    let controller=new AbortController();
    setPersonalAdvice(null);
    const load=()=>{
      controller.abort();controller=new AbortController();const request=controller;
      getCheckRecommendation(projectId,request.signal).then(value=>{if(!request.signal.aborted)setPersonalAdvice(value.recommendation)}).catch(()=>{/* Existing progress guidance stays available. */});
    };
    const updated=(event:Event)=>{if((event as CustomEvent).detail?.projectId===projectId)load()};
    load();window.addEventListener('paperstride:learning-check',updated);
    return()=>{controller.abort();window.removeEventListener('paperstride:learning-check',updated)};
  },[projectId]);
  useEffect(() => {
    const controller = new AbortController();
    setProgress([]); setSkipped([]); setFoundation(undefined); setProgressError(false);
    getLearningProgress(projectId, controller.signal).then(result => {
      if (!controller.signal.aborted) setProgress(result.items);
    }).catch(() => { if (!controller.signal.aborted) setProgressError(true); });
    const update = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.projectId !== projectId) return;
      setProgress(old => [...old.filter(item => item.node_id !== detail.nodeId),
        {node_id: detail.nodeId, status: detail.status, version: 1}]);
    };
    window.addEventListener('paperstride:learning-progress', update);
    return () => { controller.abort(); window.removeEventListener('paperstride:learning-progress', update); };
  }, [projectId]);

  const review = progress.find(item => (item.status === 'review' || item.stale) && graph?.nodes.some(node => node.id === item.node_id));
  useEffect(() => {
    setFoundation(undefined);
    if (!review) return;
    const controller = new AbortController();
    getNodeSummary(projectId, review.node_id, controller.signal).then(result => {
      if (!controller.signal.aborted && result.suggested_node) setFoundation(result.suggested_node);
    }).catch(() => { /* The original node remains the next step. */ });
    return () => controller.abort();
  }, [projectId, review?.node_id]);

  const candidates = useMemo(() => {
    const states = new Map(progress.map(item => [item.node_id, item]));
    const terms = question.toLowerCase().match(/[a-z0-9_]+|[\u3400-\u9fff]{2}/g) || [];
    return (graph?.nodes || []).filter(node => {
      const state = states.get(node.id);
      return !['paper', 'report', 'results', 'code', 'resource'].includes(node.kind) &&
        !node.hidden && !node.source_missing && !['rejected', 'disputed', 'withdrawn'].includes(node.quality_status || '') &&
        !(state?.status === 'understood' && !state.stale);
    }).map(node => ({node, score: terms.filter(term => (node.label + ' ' + node.summary).toLowerCase().includes(term)).length}))
      .sort((a, b) => b.score - a.score).map(item => item.node);
  }, [graph, question, progress]);
  const resumeSource = sources.find(source => source.id === resume?.sourceId);
  const resumeUnderstood=progress.some(item => item.node_id===resume?.nodeId && item.status==='understood' && !item.stale);
  const resumeAvailable = resume && (!resume.sourceId || !!resumeSource) && !skipped.includes('resume') && (!resumeUnderstood || !!resume.unresolvedQuestions);
  const judgmentSource=sources.find(source => source.id === (resume?.judgmentSourceId || resume?.sourceId));
  const judgmentVersion=resume?.judgmentSourceVersion || resume?.sourceVersion;
  const changed = judgmentVersion && judgmentSource?.version !== judgmentVersion;
  const reviewNode = candidates.find(node => node.id === review?.node_id);
  const candidate = candidates.find(node => !skipped.includes(node.id));
  let target: KnowledgeNode | {id: string; label: string} | undefined = candidate;
  const matched=question.toLowerCase().match(/[a-z0-9_]+|[\u3400-\u9fff]{2}/g)?.some(term =>
    ((candidate?.label || '') + ' ' + (candidate?.summary || '')).toLowerCase().includes(term));
  let reason = matched ? '从当前问题与已导入知识的词项匹配中选择起点，可更换。' : '当前问题暂无直接词项匹配，先提供一个尚未自评理解的知识点，可更换。';
  if (reviewNode && !skipped.includes(reviewNode.id)) {
    const useFoundation=foundation && !skipped.includes(foundation.id);
    target = useFoundation ? foundation : reviewNode;
    reason = useFoundation ? '你标记了需要复习，根据已保存的先修关系建议先补这一项。' : '这个知识点被标记为需要复习，或其依据版本已有变化。';
  }
  if(personalAdvice&&!skipped.includes('advice:'+personalAdvice.attempt_id)){
    return <aside className="kw-task-guidance" aria-label="当前问题的下一步">
      <h2>根据这次回答继续</h2><p>{personalAdvice.label}</p>
      <Button type="primary" onClick={()=>onLearn(personalAdvice.node_id)}>补充这一项理解</Button>
      <details><summary>为什么推荐</summary><p>{personalAdvice.question}</p><p>你的回答 · {personalAdvice.answer}</p><p>{personalAdvice.reason}</p></details>
      <Button type="text" onClick={()=>setSkipped(old=>[...old,'advice:'+personalAdvice.attempt_id])}>换一个起点</Button>
    </aside>;
  }
  if (learningRoute && onRoute && !skipped.includes('route:' + learningRoute.id)) {
    const step = learningRoute.steps.find(item => item.node_id === learningRoute.next_node_id && item.available && !item.stale);
    const needsReview = learningRoute.question_changed || learningRoute.needs_replan || (!step && learningRoute.stale);
    return <aside className="kw-task-guidance" aria-label="当前问题的下一步">
      <h2>{needsReview ? '先核对这条路线' : step ? '接着你的学习路线' : '这条路线已走完'}</h2>
      <p>{learningRoute.target_label}</p>
      {step && !needsReview && <><p>下一步 · {step.label}</p><Button type="primary" onClick={() => onLearn(step.node_id)}>继续路线学习</Button></>}
      {needsReview && <p>{learningRoute.question_changed ? '空间问题已有变化，请检查保存的目标是否仍适合。' : learningRoute.needs_replan ? '发现尚未加入路线的前置知识，请检查并重新规划。' : '部分知识或来源已变化，先核对再继续。'}</p>}
      <Button type={step && !needsReview ? 'text' : 'primary'} onClick={onRoute}>{needsReview ? '核对学习路线' : '查看与调整路线'}</Button>
      <details><summary>为什么推荐</summary><p>根据你保存的目标、步骤顺序与完成记录选择。完成一步不代表已掌握知识，可以随时跳过或调整。</p></details>
      <Button type="text" onClick={() => setSkipped(old => [...old, 'route:' + learningRoute.id])}>换一个起点</Button>
    </aside>;
  }
  if (resumeAvailable) {
    return <aside className="kw-task-guidance" aria-label="当前问题的下一步">
      <h2>接着上次的问题</h2>
      <p>{resumeDescription(resume)}</p>
      {resume.unresolvedQuestions && <blockquote>{resume.unresolvedQuestions}</blockquote>}
      {changed && <p role="status">这份资料已有变化，打开后请重新核对原判断。</p>}
      <Button type="primary" onClick={() => onResume(resume.url)}>继续上次任务</Button>
      <details><summary>为什么推荐</summary><p>根据当前账号在此浏览器中保存的暂停位置和未解决问题。</p></details>
      <Button type="text" onClick={() => setSkipped(old => [...old, 'resume'])}>换一个起点</Button>
    </aside>;
  }
  return <aside className="kw-task-guidance" aria-label="当前问题的下一步">
    <h2>{target ? '从这里开始' : sources.length ? '先读原文' : '带上你的资料'}</h2>
    <p>{target?.label || (sources.length ? '资料已保存，知识分析期间也可以阅读。' : '添加论文或研究报告，把这个问题放进资料里看。')}</p>
    <Button type="primary" onClick={() => target ? onLearn(target.id) : sources[0] ? onRead(sources[0].id) : onImport()}>
      {target ? '理解这个知识点' : sources.length ? '打开原文' : '添加资料'}
    </Button>
    {target && <><details><summary>为什么推荐</summary><p>{reason}</p></details>
      <Button type="text" onClick={() => setSkipped(old => [...old, target!.id])}>换一个起点</Button></>}
    {progressError && <p className="kw-task-muted">学习状态暂未读到，可先查阅原文或自由选择节点。</p>}
  </aside>;
}

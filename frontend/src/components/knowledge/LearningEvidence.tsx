import {useRef,useState} from 'react';
import {Button} from 'antd';
import type {KnowledgeEvidence,KnowledgeNode} from '../../api/knowledge';
import SourceFormulas from './SourceFormulas';
import {useCurrentAccount} from '../SessionContext';
import EvidenceQuote from './EvidenceQuote';

type EvidenceGroup='direct'|'context'|'other';
function readScene(key:string):{group:EvidenceGroup;limit:number;expanded:Record<string,boolean>} {
 try{const value=JSON.parse(sessionStorage.getItem(key)||'null');return {group:['direct','context','other'].includes(value?.group)?value.group:'direct',limit:typeof value?.limit==='number'&&Number.isFinite(value.limit)?Math.max(6,Math.min(2000,value.limit)):6,expanded:value?.expanded&&typeof value.expanded==='object'?value.expanded:{}}}catch{return {group:'direct',limit:6,expanded:{}}}
}

export default function LearningEvidence({node,items,onEvidence}:{node:KnowledgeNode;items:KnowledgeEvidence[];onEvidence:(e:KnowledgeEvidence)=>void}) {
 const account=useCurrentAccount(),storageKey='paperstride:learning-evidence:'+JSON.stringify([account?.id||'local',node.project_id,node.id]),saved=useRef(readScene(storageKey));
 const [group,setGroup]=useState<EvidenceGroup>(saved.current.group),[limit,setLimit]=useState(saved.current.limit),[expanded,setExpanded]=useState(saved.current.expanded);
 const persist=()=>{try{sessionStorage.setItem(storageKey,JSON.stringify(saved.current))}catch{/* Evidence remains readable without browser storage. */}};
 const exact=new Set(node.evidence_ids||[]),byContent=new Map<string,KnowledgeEvidence>();
 for(const item of items){const key=[item.source_id,item.block_id||item.id,item.source_version,(item.quote||'').trim()].join('\u0000'),previous=byContent.get(key);if(!previous||exact.has(item.id)&&!exact.has(previous.id))byContent.set(key,item)}
 const unique=[...byContent.values()],groups={direct:unique.filter(item=>item.source_id===node.source_id&&exact.has(item.id)),context:unique.filter(item=>item.source_id===node.source_id&&!exact.has(item.id)),other:unique.filter(item=>item.source_id!==node.source_id)};
 const labels={direct:'当前知识的直接依据',context:'同篇相关上下文',other:'比较与关联来源'};
 const selected=groups[group];
 return <section className="kw-learning-evidence-browser" aria-label="原文依据浏览">
  <header><h3>原文依据</h3><p>选择片段查看内容，打开原文可核对完整位置。</p></header>
  <div className="kw-evidence-groups" role="group" aria-label="依据范围">{(['direct','context','other'] as const).map(key=><button key={key} type="button" aria-pressed={group===key} onClick={event=>{setGroup(key);setLimit(6);saved.current={...saved.current,group:key,limit:6};persist();const pane=event.currentTarget.closest('.kw-learning-reader-scroll');if(pane)pane.scrollTop=0}}>{labels[key]} <span>{groups[key].length}</span></button>)}</div>
  <h4>{labels[group]}</h4>
  {group==='other'&&<p className="kw-muted">这些内容用于比较或解释关系，不代表当前方法的原作者陈述。</p>}
  {!selected.length&&<p>当前范围没有可定位片段，可查看其他依据范围或返回资料原文。</p>}
  <ol className="kw-learning-evidence-items">{selected.slice(0,limit).map((item,index)=><li key={item.id+':'+item.source_version}>
   <details className="kw-learning-evidence-card" open={expanded[item.id]??index===0} onToggle={event=>{const open=event.currentTarget.open;if(saved.current.expanded[item.id]===open)return;saved.current.expanded={...saved.current.expanded,[item.id]:open};setExpanded(saved.current.expanded);persist()}}>
    <summary><strong>{item.locator.heading||item.locator.path||'原文片段 '+(index+1)}</strong><span>{item.locator.page?'第 '+item.locator.page+' 页':item.locator.start_line?'第 '+item.locator.start_line+' 行':item.source_title}</span>{(item.source_changed||item.source_missing||item.unresolved)&&<small>来源需复核</small>}</summary>
    <div className="kw-learning-evidence-excerpt">{item.formula?<SourceFormulas items={[item.formula]} evidence={[item]} onEvidence={onEvidence}/>:<EvidenceQuote evidence={item}/>}</div>
    <footer><span>{item.source_title}</span><Button size="small" onClick={()=>onEvidence(item)}>打开原文</Button></footer>
   </details>
  </li>)}</ol>
  {selected.length>limit&&<Button onClick={()=>{const next=limit+6;setLimit(next);saved.current.limit=next;persist()}}>显示更多依据 · 还有 {selected.length-limit} 条</Button>}
 </section>;
}

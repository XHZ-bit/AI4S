import {useEffect,useState} from 'react';
import {Button,Input} from 'antd';
import type {KnowledgeEvidence,LearningResource} from '../../api/knowledge';
import {addNodeResource,getNodeResources,type KnowledgeResource,type ResourceType} from '../../api/knowledgeExperience';
import './knowledge-experience.css';

export function safeKnowledgeUrl(raw?:string){
 if(!raw||/[\u0000-\u0020\u007f\\]/.test(raw))return undefined;
 if(/^\/api\//.test(raw))return raw;
 try{const url=new URL(raw);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:undefined}catch{return undefined}
}
export function videoEmbed(raw:string){
 const safe=safeKnowledgeUrl(raw);if(!safe||safe.startsWith('/'))return undefined;
 const url=new URL(safe);if(url.protocol!=='https:')return undefined;
 let id:string|null=null;
 if(['youtube.com','www.youtube.com','m.youtube.com'].includes(url.hostname)&&url.pathname==='/watch')id=url.searchParams.get('v');
 if(url.hostname==='youtu.be')id=url.pathname.slice(1);
 if(id&&/^[A-Za-z0-9_-]{11}$/.test(id))return 'https://www.youtube-nocookie.com/embed/'+id;
 if(['bilibili.com','www.bilibili.com'].includes(url.hostname)){const bv=url.pathname.match(/^\/video\/(BV[A-Za-z0-9]{10})\/?$/)?.[1];if(bv)return 'https://player.bilibili.com/player.html?bvid='+bv+'&autoplay=0';}
 return undefined;
}
const typeLabels:Record<ResourceType,string>={paper:'论文',tutorial:'教程',image:'原文图片',code:'代码',video:'视频',search:'站外搜索'};
const accessLabels:Record<string,string>={local:'本机原文',available:'最近可访问',verified:'链接已核对',source_verified:'原作者页面提供的入口',unavailable:'最近访问未成功',not_checked:'尚未检测访问'};
function initialResource(item:LearningResource,index:number):KnowledgeResource{
 const known=item.type||item.kind||'';return {id:'saved-'+index,title:item.title||item.name||'学习资料',url:item.url||'',type:(Object.prototype.hasOwnProperty.call(typeLabels,known)?known:'tutorial') as ResourceType,reason:item.reason||item.description,origin:'saved',fetched:item.fetched};
}
export default function ResourceExplorer({projectId,nodeId,initialItems=[],onEvidence}:{projectId:string;nodeId:string;initialItems?:LearningResource[];onEvidence?:(e:KnowledgeEvidence)=>void}){
 const [items,setItems]=useState<KnowledgeResource[]>([]),[open,setOpen]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(''),[filter,setFilter]=useState('all'),[preview,setPreview]=useState<KnowledgeResource>(),[retry,setRetry]=useState(0);
 const [adding,setAdding]=useState(false),[title,setTitle]=useState(''),[url,setUrl]=useState(''),[kind,setKind]=useState<ResourceType>('tutorial'),[reason,setReason]=useState(''),[saving,setSaving]=useState(false);
 useEffect(()=>{setItems([]);setPreview(undefined);setFilter('all');setAdding(false);setTitle('');setUrl('');setReason('')},[projectId,nodeId]);
 useEffect(()=>{if(!open)return;const c=new AbortController();setLoading(true);setError('');getNodeResources(projectId,nodeId,c.signal).then(r=>setItems(r.items||[])).catch(e=>{if(!c.signal.aborted)setError(String(e))}).finally(()=>{if(!c.signal.aborted)setLoading(false)});return()=>c.abort()},[projectId,nodeId,open,retry]);
 const merged=new Map<string,KnowledgeResource>();initialItems.map(initialResource).forEach(item=>merged.set(item.url||item.id,item));items.forEach(item=>merged.set(item.url||item.id,item));
 const shown=[...merged.values()].filter(item=>filter==='all'||item.type===filter);
 async function save(){if(saving||!title.trim()||!safeKnowledgeUrl(url.trim())||!/^https?:/.test(url.trim()))return;setSaving(true);setError('');try{await addNodeResource(projectId,nodeId,{title:title.trim(),url:url.trim(),type:kind,reason:reason.trim()});setRetry(v=>v+1);setAdding(false);setTitle('');setUrl('');setReason('')}catch(e){setError(String(e))}finally{setSaving(false)}}
 return <details id="kw-learning-resources" className="kw-resource-explorer" onToggle={e=>setOpen(e.currentTarget.open)}><summary>图文、视频与代码资源{merged.size?` · ${merged.size}`:''}</summary>{open&&<div><p className="kw-muted">查看与当前知识相关的来源和学习入口；补充资源与论文原文依据分别标记。</p><div className="kw-resource-toolbar"><label>资料类型<select aria-label="筛选学习资料类型" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部类型</option>{Object.entries(typeLabels).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><Button onClick={()=>setAdding(v=>!v)}>{adding?'收起添加':'添加资源链接'}</Button><Button type="text" disabled={loading} onClick={()=>setRetry(v=>v+1)}>刷新资源</Button></div>
 {adding&&<form className="kw-resource-form" onSubmit={e=>{e.preventDefault();void save()}}><label>资源标题<input aria-label="资源标题" value={title} maxLength={250} onChange={e=>setTitle(e.target.value)} required/></label><label>资源地址<input aria-label="资源地址" value={url} maxLength={2000} onChange={e=>setUrl(e.target.value)} placeholder="https://…" type="url" required/></label><label>资源类型<select aria-label="添加的资源类型" value={kind} onChange={e=>setKind(e.target.value as ResourceType)}>{Object.entries(typeLabels).filter(([key])=>key!=='search').map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><label>与当前节点的关系<Input.TextArea aria-label="资源关系说明" value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)} autoSize={{minRows:2,maxRows:4}}/></label><Button htmlType="submit" loading={saving} disabled={!title.trim()||!/^https?:/.test(url.trim())||!safeKnowledgeUrl(url.trim())}>保存到当前空间</Button></form>}
 {loading&&<p role="status">正在读取资源…</p>}{error&&<p role="alert">资源未更新：{error}。已有入口仍可使用。</p>}{!shown.length&&!loading&&<p>当前类型尚无已保存资源，可添加原文或官方提供的链接。</p>}
 <ul className="kw-resource-list">{shown.map(item=>{const href=safeKnowledgeUrl(item.url),embed=item.type==='video'?videoEmbed(item.url):undefined;return <li key={item.id}><div><span className="kw-resource-type">{typeLabels[item.type]||'资料'}</span><strong>{href?<a href={href} target="_blank" rel="noopener noreferrer">{item.title}</a>:item.title}</strong></div>{item.reason&&<p>{item.reason}</p>}<small>{item.type==='search'?'站外搜索入口，并非已经找到的特定资源':item.fetched?'已读取来源内容，引用仍需核对适用范围':'仅资源入口，未作为全文依据'}{item.origin==='user'?' · 用户添加':''}{item.access_status&&accessLabels[item.access_status]?' · '+accessLabels[item.access_status]:''}{item.checked_at?' · 核对于 '+item.checked_at:''}</small><div className="kw-resource-actions">{embed&&<button onClick={()=>setPreview(item)}>点击播放视频</button>}{item.type==='image'&&href&&<button onClick={()=>setPreview(item)}>查看图片</button>}{item.evidence&&onEvidence&&<button onClick={()=>onEvidence(item.evidence!)}>定位原文</button>}{href&&<a href={href} target="_blank" rel="noopener noreferrer">{item.type==='search'?'前往搜索':'打开来源'}</a>}</div></li>})}</ul>
 {preview&&<section className="kw-resource-preview" aria-label="资源预览"><div><strong>{preview.title}</strong><Button onClick={()=>setPreview(undefined)}>关闭预览</Button></div>{preview.type==='video'&&videoEmbed(preview.url)?<><iframe title={preview.title} src={videoEmbed(preview.url)} sandbox="allow-scripts allow-same-origin allow-presentation" allow="fullscreen; encrypted-media" allowFullScreen referrerPolicy="no-referrer"/><p>播放器由原站提供；如无法播放，<a href={safeKnowledgeUrl(preview.url)} target="_blank" rel="noopener noreferrer">打开原站视频</a>。</p></>:preview.type==='image'&&safeKnowledgeUrl(preview.url)?<img src={safeKnowledgeUrl(preview.url)} alt={preview.title} referrerPolicy="no-referrer" onError={e=>{e.currentTarget.hidden=true;setError('图片暂时无法加载，请打开来源核对')}}/>:null}</section>}
 </div>}</details>;
}

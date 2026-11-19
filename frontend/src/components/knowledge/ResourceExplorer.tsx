import {useEffect,useRef,useState} from 'react';
import {Button,Input} from 'antd';
import {ExportOutlined} from '@ant-design/icons';
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
const typeLabels:Record<ResourceType,string>={paper:'论文',tutorial:'教程',image:'图片',code:'代码',video:'视频',search:'站外搜索'};
const accessLabels:Record<string,string>={local:'本地资料',available:'最近一次访问成功',verified:'链接已核对',source_verified:'来自作者页面',unavailable:'最近一次访问未成功',not_checked:'未检测'};
const originLabels:Record<string,string>={user:'你添加的链接',catalog:'教学资料目录',saved:'已保存的学习内容',source:'关联资料',inference:'讲解中的补充链接'};
const genericReasons=new Set(['站外搜索入口；不是已经核验的具体资源','与当前知识关联的补充入口']);
function isSearchResource(item:KnowledgeResource){
 if(item.type==='search'||item.origin==='search')return true;
 const href=safeKnowledgeUrl(item.url);
 if(!href||href.startsWith('/'))return false;
 const url=new URL(href);
 return url.hostname==='search.bilibili.com'||(['youtube.com','www.youtube.com'].includes(url.hostname)&&url.pathname==='/results')||(url.hostname==='scholar.google.com'&&url.pathname==='/scholar');
}
function searchLabel(item:KnowledgeResource){
 const href=safeKnowledgeUrl(item.url);
 if(href&&!href.startsWith('/')){
  const host=new URL(href).hostname;
  if(host==='search.bilibili.com')return '哔哩哔哩';
  if(['youtube.com','www.youtube.com'].includes(host))return 'YouTube';
  if(host==='scholar.google.com')return '学术搜索';
 }
 return item.title;
}
function sourceLabel(item:KnowledgeResource){
 const href=safeKnowledgeUrl(item.url);
 return href?.startsWith('/')?'本地资料':href?new URL(href).hostname.replace(/^www\./,''):'';
}
function initialResource(item:LearningResource,index:number):KnowledgeResource{
 const known=item.type||item.kind||'';return {id:'saved-'+index,title:item.title||item.name||'学习资料',url:item.url||'',type:(Object.prototype.hasOwnProperty.call(typeLabels,known)?known:'tutorial') as ResourceType,reason:item.reason||item.description,origin:item.origin||'saved',fetched:item.fetched,access_status:item.access_status,checked_at:item.checked_at,evidence:item.evidence};
}
export default function ResourceExplorer({projectId,nodeId,initialItems=[],onEvidence}:{projectId:string;nodeId:string;initialItems?:LearningResource[];onEvidence?:(e:KnowledgeEvidence)=>void}){
 const scope=projectId+':'+nodeId;
 const [result,setResult]=useState<{scope:string;items:KnowledgeResource[]}>(),[open,setOpen]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState<{kind:'load'|'save'|'image';detail:string}>(),[filter,setFilter]=useState('all'),[preview,setPreview]=useState<KnowledgeResource>(),[retry,setRetry]=useState(0),[notice,setNotice]=useState('');
 const [adding,setAdding]=useState(false),[title,setTitle]=useState(''),[url,setUrl]=useState(''),[kind,setKind]=useState<ResourceType>('tutorial'),[reason,setReason]=useState(''),[saving,setSaving]=useState(false);
 const generation=useRef(0),inFlight=useRef(false),urlInput=useRef<HTMLInputElement>(null);
 useEffect(()=>{generation.current++;inFlight.current=false;setResult(undefined);setPreview(undefined);setFilter('all');setAdding(false);setTitle('');setUrl('');setReason('');setSaving(false);setError(undefined);setNotice('');return()=>{generation.current++}},[scope]);
 useEffect(()=>{if(!open)return;const c=new AbortController();setLoading(true);setError(undefined);getNodeResources(projectId,nodeId,c.signal).then(r=>{if(!c.signal.aborted)setResult({scope,items:r.items||[]})}).catch(e=>{if(!c.signal.aborted)setError({kind:'load',detail:String(e)})}).finally(()=>{if(!c.signal.aborted)setLoading(false)});return()=>c.abort()},[projectId,nodeId,scope,open,retry]);
 const merged=new Map<string,KnowledgeResource>();initialItems.map(initialResource).forEach(item=>merged.set(item.url||item.id,item));(result?.scope===scope?result.items:[]).forEach(item=>merged.set(item.url||item.id,item));
 const all=[...merged.values()],resources=all.filter(item=>!isSearchResource(item)),searches=all.filter(item=>isSearchResource(item)&&safeKnowledgeUrl(item.url));
 const shown=resources.filter(item=>filter==='all'||item.type===filter);
 async function save(){
  if(inFlight.current||!title.trim()||!safeKnowledgeUrl(url.trim())||!/^https?:/.test(url.trim()))return;
  const gen=generation.current;inFlight.current=true;setSaving(true);setError(undefined);setNotice('');
  try{const item=await addNodeResource(projectId,nodeId,{title:title.trim(),url:url.trim(),type:kind,reason:reason.trim()});if(gen!==generation.current)return;
   setResult(old=>({scope,items:[...(old?.scope===scope?old.items:[]).filter(previous=>previous.url!==item.url),item]}));setRetry(v=>v+1);setAdding(false);setTitle('');setUrl('');setReason('');setNotice('链接已保存');
  }catch(e){if(gen===generation.current)setError({kind:'save',detail:String(e)})}finally{if(gen===generation.current){setSaving(false);inFlight.current=false}}
 }
 function replaceLink(item:KnowledgeResource){setAdding(true);setTitle(item.title);setKind(item.type==='search'?'tutorial':item.type);setReason(item.reason||'');setUrl('');setNotice('');requestAnimationFrame(()=>urlInput.current?.focus())}
 return <details id="kw-learning-resources" className="kw-resource-explorer" onToggle={e=>{if(e.target===e.currentTarget)setOpen(e.currentTarget.open)}}><summary>学习资料{resources.length?` · ${resources.length}`:''}</summary>{open&&<div>
 <div className="kw-resource-toolbar">{!!resources.length&&<label>资料类型<select aria-label="筛选学习资料类型" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部类型</option>{Object.entries(typeLabels).filter(([value])=>value!=='search').map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>}<Button onClick={()=>setAdding(v=>!v)}>{adding?'收起添加':'添加资源链接'}</Button><Button type="text" disabled={loading} onClick={()=>setRetry(v=>v+1)}>刷新资源</Button></div>
 {adding&&<form className="kw-resource-form" onSubmit={e=>{e.preventDefault();void save()}}><label>资源标题<input aria-label="资源标题" value={title} maxLength={250} onChange={e=>setTitle(e.target.value)} disabled={saving} required/></label><label>资源地址<input ref={urlInput} aria-label="资源地址" value={url} maxLength={2000} onChange={e=>setUrl(e.target.value)} placeholder="https://…" type="url" disabled={saving} required/></label><label>资源类型<select aria-label="添加的资源类型" value={kind} onChange={e=>setKind(e.target.value as ResourceType)} disabled={saving}>{Object.entries(typeLabels).filter(([key])=>key!=='search').map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><label>与当前节点的关系<Input.TextArea aria-label="资源关系说明" value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)} autoSize={{minRows:2,maxRows:4}} disabled={saving}/></label><Button htmlType="submit" loading={saving} disabled={!title.trim()||!/^https?:/.test(url.trim())||!safeKnowledgeUrl(url.trim())}>保存到当前空间</Button></form>}
 {loading&&<p role="status">读取学习资料…</p>}{notice&&<p role="status">{notice}</p>}
 {error&&<div className="kw-resource-error" role="alert"><p>{error.kind==='save'?'链接未保存，输入已保留。':error.kind==='image'?'图片未能加载，可打开原链接查看。':'学习资料暂时无法更新，已显示的内容仍可使用。'}{error.kind!=='image'&&<Button type="link" disabled={saving||loading} onClick={()=>error.kind==='save'?void save():setRetry(v=>v+1)}>重试</Button>}</p><details><summary>错误详情</summary><p>{error.detail}</p></details></div>}
 {!shown.length&&!loading&&!error&&<p className="kw-resource-empty">{resources.length?'没有这类资料，可切换类型或添加链接。':'还没有保存学习资料，可添加课程、代码或视频链接。'}</p>}
 {!!shown.length&&<ul className="kw-resource-list" aria-label="已保存学习资料">{shown.map(item=>{const href=safeKnowledgeUrl(item.url),embed=item.type==='video'?videoEmbed(item.url):undefined;return <li key={item.id}><div><span className="kw-resource-type">{typeLabels[item.type]||'资料'}</span><strong>{href?<a href={href} target="_blank" rel="noopener noreferrer">{item.title}</a>:item.title}</strong></div>
  <small className="kw-resource-host">{sourceLabel(item)}</small>{item.reason&&!genericReasons.has(item.reason.trim())&&<p>{item.reason}</p>}
  {(!href||item.access_status==='unavailable')&&<p className="kw-resource-link-issue">{href?'这个链接最近一次访问未成功。':'链接地址需要更新。'}<Button size="small" type="link" onClick={()=>replaceLink(item)}>添加替代链接</Button></p>}
  <div className="kw-resource-actions">{embed&&<button onClick={()=>setPreview(item)}>点击播放视频</button>}{item.type==='image'&&href&&<button onClick={()=>setPreview(item)}>查看图片</button>}{item.evidence&&onEvidence&&<button onClick={()=>onEvidence(item.evidence!)}>定位原文</button>}</div>
  <details className="kw-resource-details"><summary>资源详情</summary><dl><dt>来源</dt><dd>{originLabels[item.origin||'']||'关联学习资料'}</dd><dt>内容</dt><dd>{item.fetched?'包含已读取内容':'资源链接'}</dd>{item.access_status&&accessLabels[item.access_status]&&<><dt>访问记录</dt><dd>{accessLabels[item.access_status]}</dd></>}{item.checked_at&&<><dt>核对日期</dt><dd>{item.checked_at}</dd></>}{href&&<><dt>地址</dt><dd>{href}</dd></>}{item.reason&&genericReasons.has(item.reason.trim())&&<><dt>说明</dt><dd>{item.reason}</dd></>}</dl></details>
 </li>})}</ul>}
 {!!searches.length&&<nav className="kw-resource-searches" aria-label="站外搜索"><span>站外搜索</span><div>{searches.map(item=><a key={item.id} href={safeKnowledgeUrl(item.url)} target="_blank" rel="noopener noreferrer">{searchLabel(item)}<ExportOutlined aria-hidden/></a>)}</div></nav>}
 {preview&&<section className="kw-resource-preview" aria-label="资源预览"><div><strong>{preview.title}</strong><Button onClick={()=>setPreview(undefined)}>关闭预览</Button></div>{preview.type==='video'&&videoEmbed(preview.url)?<><iframe title={preview.title} src={videoEmbed(preview.url)} sandbox="allow-scripts allow-same-origin allow-presentation" allow="fullscreen; encrypted-media" allowFullScreen referrerPolicy="no-referrer"/><p>如无法播放，<a href={safeKnowledgeUrl(preview.url)} target="_blank" rel="noopener noreferrer">打开原站视频</a>。</p></>:preview.type==='image'&&safeKnowledgeUrl(preview.url)?<><img src={safeKnowledgeUrl(preview.url)} alt={preview.title} referrerPolicy="no-referrer" onError={e=>{e.currentTarget.hidden=true;setError({kind:'image',detail:'图片加载失败'})}}/><a href={safeKnowledgeUrl(preview.url)} target="_blank" rel="noopener noreferrer">打开原图</a></>:null}</section>}
 </div>}</details>;
}

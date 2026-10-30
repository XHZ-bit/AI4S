import {useEffect,useRef,useState} from 'react';
import {Alert,Button} from 'antd';
import {useSearchParams} from 'react-router-dom';
import {apiGet,apiPost} from '../../api/client';
import {useInspector} from '../workspace/InspectorContext';
import {safeReturnTo} from '../../api/workContext';
const fields=['paper','page','panel','ref','focus','session','lesson','step','activity','unit','returnTo','document_id','document_version'] as const;
export default function SceneSync({projectId,view}:{projectId:string;view:string}){
 const [params,setParams]=useSearchParams();const inspector=useInspector();const initial=useRef(new URLSearchParams(params)),restored=useRef(false);const [ready,setReady]=useState(false),[version,setVersion]=useState(0),[error,setError]=useState(''),[conflict,setConflict]=useState<any>(),[retry,setRetry]=useState(0);const writing=useRef(false),last=useRef('');
 const latestInspector=useRef(inspector);latestInspector.current=inspector;
 const restore=(data:any,explicit:boolean)=>{const input=explicit?initial.current:new URLSearchParams();const paperCompatible=!input.get('paper')||input.get('paper')===data.paper;const explicitSource=['page','ref','document_id'].some(k=>input.has(k));setParams(old=>{const n=new URLSearchParams(old);if(!input.has('tab')&&data.view)n.set('tab',data.view);for(const key of fields){if(explicit&&input.has(key))continue;if(!paperCompatible)continue;if(explicitSource&&['page','ref','focus','document_id','document_version','session','step','panel'].includes(key))continue;const value=data[key];if(key==='returnTo'&&!safeReturnTo(value))continue;if(value!==null&&value!==undefined)n.set(key,String(value));else if(!explicit)n.delete(key)}return n},{replace:true});if(paperCompatible&&!explicitSource&&data.selection&&data.paper)latestInspector.current.restoreSelection?.({...data.selection,paper_uid:data.paper});};
 useEffect(()=>{let live=true;void apiGet<any>(`/api/workbench/projects/${projectId}/scene`).then(r=>{if(!live)return;setVersion(r.version);if(!restored.current){restore(r.data,true);restored.current=true}setReady(true);setError('')}).catch(e=>{if(live)setError('工作现场恢复失败，当前内容仍可使用：'+String(e))});return()=>{live=false}},[projectId,retry]);
 const paper=params.get('paper');const selected=inspector.selection;
 const body:any={view,...Object.fromEntries(fields.map(key=>[key,params.get(key)]))};for(const key of ['page','step'])body[key]=body[key]!==null?Number(body[key]):null;
 body.selection=selected?.paper_uid===paper&&selected.document_id&&selected.page?{document_id:selected.document_id,document_version:selected.document_version,page:selected.page,quote:selected.quote}:null;
 const signature=JSON.stringify(body);
 useEffect(()=>{if(!ready||conflict||signature===last.current)return;const timer=setTimeout(async()=>{if(writing.current)return;writing.current=true;try{const r=await apiPost<any>(`/api/workbench/projects/${projectId}/scene`,{...JSON.parse(signature),version});last.current=signature;setVersion(r.version);setError('')}catch(e:any){setError('工作现场尚未同步，当前位置仍保留');if(e.status===409)try{setConflict(await apiGet(`/api/workbench/projects/${projectId}/scene`))}catch{}}finally{writing.current=false}},700);return()=>clearTimeout(timer)},[ready,signature,version,conflict,retry,projectId]);
 if(!error)return null;
 return <Alert type="warning" message={error} action={conflict?<><Button onClick={()=>{setVersion(conflict.version);setConflict(undefined)}}>保留当前位置</Button><Button onClick={()=>{setVersion(conflict.version);restore(conflict.data,false);last.current='';setConflict(undefined)}}>恢复另一设备位置</Button></>:<Button onClick={()=>setRetry(x=>x+1)}>重试同步</Button>}/>;
}

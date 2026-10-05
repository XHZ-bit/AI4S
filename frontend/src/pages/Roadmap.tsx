import {useEffect,useState,useRef} from "react";
import {useSearchParams,Link} from "react-router-dom";
import {Alert,Button,Card,Checkbox,Form,Input,InputNumber,Select,Space,Tag,Typography,message} from "antd";
import EvidenceButton from "../components/EvidenceButton";
import {apiGet,apiPost,apiPatch} from "../api/client";
import {getRoadmap,listRoadmaps,type RoadmapResult} from "../api/roadmap";
export default function Roadmap(){
 const [params,setParams]=useSearchParams();const [result,setResult]=useState<RoadmapResult|null>(null);const [history,setHistory]=useState<any[]>([]);const [error,setError]=useState("");const [loading,setLoading]=useState(false);const [saving,setSaving]=useState(false);const lock=useRef(false);const [targets,setTargets]=useState<any[]>([]);
 const [form]=Form.useForm();
 useEffect(()=>{let live=true;listRoadmaps().then(r=>{if(live)setHistory(r.items);}).catch(e=>{if(live)setError(String(e));});const id=Number(params.get("id"));if(id)getRoadmap(id).then(r=>{if(live)setResult(r);}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;};},[params]);
 return <Space direction="vertical" size="large" style={{width:"100%"}}><Typography.Title level={2}>科研路线推荐</Typography.Title>
 <Alert type="info" message="正式路线只使用已核验的必要先修关系" description="资料不足时会说明缺口。完成阅读不等于掌握，模型建议不代表经实测的复现路径。"/>
 {error&&<Alert type="error" message={error} closable onClose={()=>setError("")}/>}
 <Card title="学习者画像"><Form form={form} initialValues={{weekly_hours:10}} onFinish={async v=>{setLoading(true);try{const known=(v.known_concepts||"").split(/[,，]/).map((s:string)=>s.trim()).filter(Boolean);await apiPost("/api/roadmap/generate-async",{profile:{goal:v.goal,target_uid:v.target_uid,known_concepts:known,weekly_hours:v.weekly_hours}});message.success("路线任务已提交，请在处理进度打开完成结果");}catch(e){setError(String(e));}finally{setLoading(false);}}}>
 <Form.Item name="goal" label="学习目标" rules={[{required:true}]}><Input placeholder="如：3个月入门具身智能，复现Diffusion Policy"/></Form.Item>
 <Form.Item name="target_uid" label="确认目标实体" rules={[{required:true,message:"请搜索并选择图谱中的目标，避免误匹配"}]}><Select showSearch filterOption={false} placeholder="输入方法或概念名称" onSearch={async q=>{try{const r=await apiGet<any>("/api/graph/nodes",{q});setTargets(r.items.filter((n:any)=>["concept","method"].includes(n.type)));}catch(e){setError(String(e));}}} options={targets.map(t=>({value:t.uid,label:`${t.name} · ${t.type}`}))}/></Form.Item>
 <Form.Item name="known_concepts" label="已掌握概念"><Input placeholder="逗号分隔；有歧义的名称需要进一步确认"/></Form.Item><Form.Item name="weekly_hours" label="每周小时"><InputNumber min={1} max={80}/></Form.Item><Button htmlType="submit" type="primary" loading={loading}>生成路线</Button> <Link to="/tasks">查看处理进度</Link></Form></Card>
 <Select allowClear style={{width:"100%"}} placeholder="打开已保存路线" value={result?.id||undefined} onChange={id=>{if(id)setParams({id:String(id)});else{setResult(null);setParams({});}}} options={history.map(r=>({value:r.id,label:`${r.goal} · ${r.created_at}`}))}/>
 {result&&<>{(result as any).stale&&<Alert type="warning" message="路线引用的知识已发生变更，请重新规划；已完成记录仍保留。"/>}{result.phases.map(ph=><Card key={ph.phase} title={`${ph.title.replace(/^(concept|method):/,"").replace(/-/g," ")} · ${ph.weeks}`}>{ph.items.map((item,idx)=><div key={item.task_id||idx} style={{marginBottom:16}}><Checkbox disabled={saving} checked={item.done} onChange={async e=>{if(lock.current)return;lock.current=true;setSaving(true);try{setResult(await apiPatch<RoadmapResult>(`/api/roadmap/${result.id}/progress`,{task_id:item.task_id,phase:ph.phase,item_index:idx,version:result.version,done:e.target.checked}));}catch(e){setError(String(e));}finally{lock.current=false;setSaving(false);}}}>{item.title}</Checkbox><Tag>{item.kind}</Tag><p>{item.reason}</p><p>依据：{item.evidence}</p>{item.evidence_ids?.map(id=><EvidenceButton key={id} id={id}/>)}{item.kind==="paper"&&item.uid&&<Link to={`/papers/${item.uid}`}>进入论文工作区</Link>}</div>)}</Card>)}
 <Typography.Title level={3}>待验证研究问题</Typography.Title>{result.innovations.map((q,i)=><Card key={i} title={q.title}><p>{q.rationale}</p><p>{q.evidence}</p><Tag>假设，不代表研究空白或创新性认证</Tag></Card>)}</>}
 </Space>;
}

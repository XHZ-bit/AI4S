import {useEffect,useState} from "react";
import {Alert,Button,Space,Table,Tag,Typography} from "antd";
import {Link} from "react-router-dom";
import {apiGet,apiPost} from "../api/client";
export default function Tasks(){
 const [items,setItems]=useState<any[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState<number|null>(null);
 useEffect(()=>{let live=true;const poll=()=>apiGet<any>("/api/learning/tasks").then(r=>{if(live){setItems(r.items);setError("");}}).catch(e=>{if(live)setError(String(e));});poll();const id=setInterval(poll,3000);return()=>{live=false;clearInterval(id);};},[]);
 return <><Typography.Title level={2}>处理进度</Typography.Title><Typography.Paragraph>离开页面不会停止后台处理。重启中断或失败的任务可以重新执行；原文件和已保存的学习记录会保留。</Typography.Paragraph>
 {error&&<Alert type="error" message={error}/>}<Table<any> rowKey="id" dataSource={items} scroll={{x:850}} columns={[
 {title:"任务",dataIndex:"id"},{title:"类型",dataIndex:"type"},{title:"对象",render:(_,r)=>{const p=JSON.parse(r.params_json);return p.uid?<Link to={`/papers/${p.uid}`}>{p.uid}</Link>:p.profile?.goal||"论文采集";}},
 {title:"状态",dataIndex:"status",render:s=><Tag color={s==="done"?"green":s==="failed"?"red":"blue"}>{{queued:"排队中",running:"处理中",done:"已完成",failed:"未完成"}[s as string]||s}</Tag>},
 {title:"更新时间",dataIndex:"updated_at"},{title:"原因",render:(_,r)=>r.error||(r.result_json&&JSON.parse(r.result_json)?.warnings?.map((w:any)=>`${w.stage}: ${w.error}`).join("；"))},
 {title:"操作",render:(_,r)=><Space>{(r.status==="failed"||(r.status==="done"&&r.result_json&&JSON.parse(r.result_json)?.warnings?.length))&&<Button loading={busy===r.id} onClick={async()=>{setBusy(r.id);try{await apiPost(`/api/learning/tasks/${r.id}/retry`);setError("");}catch(e){setError(String(e));}finally{setBusy(null);}}}>重试</Button>}{r.type==="roadmap"&&r.status==="done"&&<Link to={`/roadmap?id=${JSON.parse(r.result_json)?.id}`}>打开路线</Link>}</Space>}
 ]}/></>;
}

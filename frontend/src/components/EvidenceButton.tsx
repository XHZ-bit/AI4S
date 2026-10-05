import {useState} from "react";
import {Button,Modal,Typography,message} from "antd";
import {apiGet} from "../api/client";
export default function EvidenceButton({id}:{id:string}){
 const [data,setData]=useState<any>();const [busy,setBusy]=useState(false);
 return <><Button size="small" loading={busy} onClick={async()=>{setBusy(true);try{setData(await apiGet(`/api/learning/evidence/${id}`));}catch(e){message.error(String(e));}finally{setBusy(false);}}}>原文依据</Button><Modal open={!!data} footer={null} onCancel={()=>setData(undefined)} title={data?.heading} width={800}><p>{data?.page?`第 ${data.page} 页`:"没有可靠页码"} · 文档版本 {data?.document_id}</p><Typography.Paragraph style={{whiteSpace:"pre-wrap"}}>{data?.text}</Typography.Paragraph></Modal></>;
}

import {useState} from "react";
import {Alert,Button,Form,Input,Select,Space,message} from "antd";
import {apiPost} from "../api/client";
export default function CurationSources({onSaved}:{onSaved:()=>void}){
 const [busy,setBusy]=useState(false);
 const types=["concept","method","paper","dataset","benchmark","resource","author"];
 return <Space direction="vertical" style={{width:"100%"}}>
 <Alert type="info" message="录入教材、课程或论文中的原文依据" description="录入只创建候选；需要在知识候选页核验后才能参与正式路线。请勿用模型生成的说明冒充原文。"/>
 <Form layout="vertical" initialValues={{heading:"教学依据",rel_type:"PREREQUISITE_OF",src_type:"concept",dst_type:"concept"}} onFinish={async v=>{setBusy(true);try{await apiPost("/api/learning/sources",v);message.success("已创建候选，等待核验");onSaved();}catch(e){message.error(String(e));}finally{setBusy(false);}}}>
 {([["title","资料标题"],["source_url","来源 HTTPS 链接"],["heading","章节"],["actor","录入维护者"]] as string[][]).map(([name,label])=><Form.Item key={name} name={name} label={label} rules={[{required:true}]}><Input/></Form.Item>)}
 <Form.Item name="text" label="原文段落及必要上下文" rules={[{required:true}]}><Input.TextArea rows={6}/></Form.Item>
 <Form.Item name="quote" label="支持关系的连续逐字原文" rules={[{required:true}]}><Input.TextArea rows={3}/></Form.Item>
 <Space wrap><Form.Item name="src_name" label="起点名称" rules={[{required:true}]}><Input/></Form.Item><Form.Item name="src_type" label="起点类型"><Select style={{width:150}} options={types.map(t=>({value:t,label:t}))}/></Form.Item><Form.Item name="rel_type" label="关系"><Select style={{width:200}} options={["PREREQUISITE_OF","USES","PROPOSES","SUBTOPIC_OF","HAS_RESOURCE","COMPARED_WITH","IMPROVES_ON","EVALUATES_ON"].map(t=>({value:t,label:t}))}/></Form.Item><Form.Item name="dst_name" label="终点名称" rules={[{required:true}]}><Input/></Form.Item><Form.Item name="dst_type" label="终点类型"><Select style={{width:150}} options={types.map(t=>({value:t,label:t}))}/></Form.Item></Space>
 <Form.Item name="conditions" label="适用条件与备注"><Input.TextArea/></Form.Item><Button htmlType="submit" type="primary" loading={busy}>保存候选证据</Button>
 </Form></Space>;
}

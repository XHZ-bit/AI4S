import {useEffect,useState} from "react";
import {Alert,Button,Input,Select,Switch} from "antd";
import {Link} from "react-router-dom";
import {apiGet,apiPost} from "../../api/client";
import {featureLabels,type Feature} from "../../api/preferences";
import {usePreferences} from "../PreferencesContext";
export default function LearningDashboard({onScope}:{onScope:(name:string,features?:Record<Feature,boolean>)=>void}){
 const {preferences}=usePreferences();
 const [data,setData]=useState<any>(),[error,setError]=useState(""),[name,setName]=useState(""),[features,setFeatures]=useState(preferences.features),[selected,setSelected]=useState("");
 const refresh=()=>apiGet<any>("/api/tutor/dashboard").then(setData).catch(e=>setError(String(e)));
 useEffect(()=>{void refresh();},[]);
 return <details className="learning-records"><summary>学习档案、课题偏好与调用记录</summary>{error&&<Alert type="error" message={error}/>}<Button onClick={()=>void refresh()}>刷新记录</Button>
 <h3>知识点检查</h3><p>依据不同题目的最近作答整理；通过检查后仍建议用新例子和代码验证。</p>{data?.knowledge.map((k:any)=><p key={k.id}><Link to={`/learn?view=foundations&lesson=${k.id}`}>{k.title}</Link>：{k.state} · {k.correct}/{k.total} 题答对</p>)}
 <h3>当前学习课题</h3><p>每个课题可以减少辅导内容；个人设置中关闭的功能不会被重新开启。</p><Select aria-label="当前学习课题" style={{width:"100%"}} value={selected} options={[{value:"",label:"使用个人默认偏好"},...(data?.scopes||[]).map((s:any)=>({value:s.name,label:s.name}))]} onChange={value=>{setSelected(value);const item=data?.scopes.find((s:any)=>s.name===value);onScope(value,item?.features);if(item){setName(value);setFeatures(item.features);}}}/>
 <details><summary>新增或修改课题偏好</summary><Input aria-label="学习课题名称" placeholder="例如：机器人策略学习" maxLength={100} value={name} onChange={e=>setName(e.target.value)}/>{(Object.keys(featureLabels) as Feature[]).filter(k=>["foundations","glossary","quizzes","coding"].includes(k)).map(k=><p key={k}><Switch aria-label={`课题${featureLabels[k][0]}`} checked={features[k]} disabled={!preferences.features[k]} onChange={v=>setFeatures(f=>({...f,[k]:v}))}/> {featureLabels[k][0]}</p>)}<Button disabled={!name.trim()} onClick={async()=>{try{await apiPost("/api/tutor/scopes",{name:name.trim(),features});await refresh();setSelected(name.trim());onScope(name.trim(),features);setError("");}catch(e){setError(String(e));}}}>保存并使用课题偏好</Button></details>
 <h3>最近模型调用</h3><p>Token 数由提供商返回；未提供时显示“未提供”，不估算费用。</p>{!data?.usage.length&&<p>暂无调用记录</p>}{data?.usage.map((u:any)=><p key={u.id}>{u.model} · {u.status==="completed"?"已返回":"未成功"} · {u.seconds} 秒 · 输入 {u.input_tokens??"未提供"} / 输出 {u.output_tokens??"未提供"} token · {u.created_at} UTC</p>)}</details>;
}

import AccountServices from "../components/workbench/AccountServices";
import AuthenticationForm from "../components/AuthenticationForm";
import PasswordChangeForm from "../components/PasswordChangeForm";
import Notebook from "../components/workbench/Notebook";
import {useEffect,useState} from "react";
import {useSearchParams} from "react-router-dom";
import {Alert,Avatar,Button,Checkbox,Form,Input,InputNumber,Radio,Space,Switch,message} from "antd";
import {UserOutlined,UploadOutlined} from "@ant-design/icons";
import {usePreferences} from "../components/PreferencesContext";
import {featureLabels,presets,savePreferences,type Feature,type Preferences} from "../api/preferences";
import {authenticatedFetch,clearBrowserDrafts,getSession,logout,notifyAccountChanged,type Session} from "../api/session";
import {apiPost} from "../api/client";
import "./settings.css";

export default function Settings(){
 const {preferences,adopt,loading,error:loadError}=usePreferences();
 const [params,setParams]=useSearchParams();const tab=["profile","learning","model","account","notebook"].includes(params.get("tab")||"")?params.get("tab")!:"profile";const setTab=(value:string)=>setParams({tab:value});
 const [draft,setDraft]=useState<Preferences>(preferences),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [session,setSession]=useState<Session>(),[avatarRevision,setAvatarRevision]=useState(0);
 useEffect(()=>setDraft(preferences),[preferences]);
 useEffect(()=>{getSession().then(setSession).catch(e=>setError(String(e)));},[]);
 const dirty=JSON.stringify(draft)!==JSON.stringify(preferences);
 const save=async()=>{setBusy(true);setError("");try{const value=await savePreferences(draft);adopt(value);setDraft(value);message.success("个人设置已保存");}catch(e){setError(String(e));}finally{setBusy(false);}};
 const profile=(name:keyof Preferences["profile"],value:unknown)=>setDraft(d=>({...d,profile:{...d.profile,[name]:value}}));
 const provider=(name:string,value:unknown)=>setDraft(d=>({...d,provider:{...d.provider,[name]:value}}));
 return <div className="personal-settings"><header><h1>个人设置</h1><p>选择适合你的研究方式，随时调整学习深度。</p></header>
  {(error||loadError)&&<Alert type="error" closable message={error||loadError} onClose={()=>setError("")}/>}
  <div className="settings-layout"><nav aria-label="个人设置分类">{[["profile","个人资料"],["learning","学习与功能"],["model","辅导模型"],["account","账号与安全"],["notebook","我的笔记"]].map(([key,label])=><button key={key} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
   <div className="settings-content">
    {tab==="profile"&&<section><h2>个人资料</h2><div className="settings-avatar"><Avatar size={80} src={draft.avatar_url?draft.avatar_url+`?v=${avatarRevision}`:undefined} icon={<UserOutlined/>}/><div><label className="settings-upload"><UploadOutlined/> 上传头像<input aria-label="上传头像" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError("");try{const body=new FormData();body.append("file",file);const response=await authenticatedFetch("/api/preferences/avatar",{method:"POST",body});if(!response.ok)throw new Error((await response.json()).detail);const avatar=await response.json();setDraft(d=>({...d,avatar_url:avatar.avatar_url}));setAvatarRevision(Date.now());message.success("头像已更新");}catch(caught){setError(String(caught));}finally{e.target.value="";setBusy(false);}}}/></label><p>PNG、JPEG 或 WebP，最大 2MB</p>{draft.avatar_url&&<Button size="small" type="text" onClick={async()=>{const response=await authenticatedFetch("/api/preferences/avatar",{method:"DELETE"});if(response.ok){setDraft(d=>({...d,avatar_url:null}));}else setError("移除失败，请重试");}}>移除头像</Button>}</div></div>
     <Form layout="vertical"><Form.Item label="显示名称"><Input aria-label="显示名称" value={draft.profile.display_name} onChange={e=>profile("display_name",e.target.value)} maxLength={50} placeholder="你希望导师如何称呼你"/></Form.Item><Form.Item label="学校或机构"><Input aria-label="学校或机构" value={draft.profile.institution} onChange={e=>profile("institution",e.target.value)} maxLength={120}/></Form.Item><Form.Item label="研究兴趣"><Input aria-label="研究兴趣" value={draft.profile.interests} onChange={e=>profile("interests",e.target.value)} maxLength={300} placeholder="例如：机器人学习、生成模型"/></Form.Item><Form.Item label="个人简介"><Input.TextArea aria-label="个人简介" rows={3} value={draft.profile.bio} onChange={e=>profile("bio",e.target.value)} maxLength={500}/></Form.Item></Form>
    </section>}
    {tab==="learning"&&<section><h2>按你的节奏学习</h2><p>先选择起点，再逐项调整。切换模式会更新下方开关，保存后生效。</p><Radio.Group className="settings-presets" value={draft.profile.level} onChange={e=>setDraft(d=>({...d,profile:{...d.profile,level:e.target.value},features:{...presets[e.target.value]}}))}>{[["beginner","新手学习","从基础到代码，逐步练习"],["reader","论文精读","关注概念、方法和理解检查"],["researcher","科研规划","关注论文关系与研究路线"]].map(([key,title,detail])=><Radio.Button key={key} value={key}><strong>{title}</strong><span>{detail}</span></Radio.Button>)}</Radio.Group>
     <div className="settings-feature-list">{(Object.keys(featureLabels) as Feature[]).map(key=><label key={key}><div><strong>{featureLabels[key][0]}</strong><p>{featureLabels[key][1]}</p></div><Switch aria-label={featureLabels[key][0]} checked={draft.features[key]} onChange={checked=>setDraft(d=>({...d,features:{...d.features,[key]:checked}}))}/></label>)}</div><Form layout="vertical"><Form.Item label="每周可投入时间"><InputNumber aria-label="每周可投入小时" min={1} max={80} addonAfter="小时" value={draft.profile.weekly_hours} onChange={value=>profile("weekly_hours",value||5)}/></Form.Item></Form><p>关闭的内容会从导航和阅读页面隐藏，也不会触发相应的辅导生成请求。已有记录会保留。</p>
    </section>}
    {tab==="model"&&<section><h2>选择辅导模型</h2><p>默认使用平台预设的 <strong>{preferences.default_model||"Qwen"}</strong>。自定义配置仅用于个人辅导、连接测试和论文辅助解读。</p><label className="settings-provider-toggle"><span>使用自定义模型</span><Switch aria-label="使用自定义模型" checked={draft.provider.enabled} onChange={value=>provider("enabled",value)}/></label>
     {draft.provider.enabled?<Form layout="vertical"><Form.Item label="API Base URL" extra="支持 OpenAI 兼容的 Chat Completions 接口；填写 /v1 等基础地址，不要包含 /chat/completions。"><Input aria-label="API Base URL" value={draft.provider.base_url} onChange={e=>provider("base_url",e.target.value)} placeholder="https://api.example.com/v1"/></Form.Item><Form.Item label="模型名称"><Input aria-label="模型名称" value={draft.provider.model} onChange={e=>provider("model",e.target.value)} placeholder="填写提供商的模型标识"/></Form.Item><Form.Item label="API Key" extra={preferences.provider.has_key?"已保存密钥，留空可继续使用。浏览器不会回显密钥。":"密钥将加密保存在服务端。"}><Input.Password aria-label="API Key" autoComplete="off" value={draft.provider.api_key||""} onChange={e=>provider("api_key",e.target.value)}/></Form.Item><Checkbox checked={!!draft.provider.clear_key} onChange={e=>provider("clear_key",e.target.checked)}>删除已保存的密钥</Checkbox></Form>:<div className="settings-default-model"><strong>使用平台预设模型</strong><p>无需填写密钥，可以直接开始辅导。</p></div>}
     <Space wrap><Button disabled={dirty||busy} onClick={async()=>{setBusy(true);setError("");try{const result=await apiPost<{model:string}>("/api/preferences/test-model");message.success(`连接成功：${result.model}`);}catch(e){setError(String(e));}finally{setBusy(false);}}}>测试已保存的配置</Button>{dirty&&<span>请先保存，再测试连接</span>}</Space><p className="settings-model-note">开始辅导时，问题和所选原文片段会发送到当前模型提供商。自定义地址需为公开 HTTPS 服务。</p>
    </section>}
    {tab==="account"&&<section><h2>账号与安全</h2>
      {session?.user ? <>
        <div className="atlas-account-identity"><div><strong>{session.user.username}</strong><p>{session.user.role === "admin" ? "管理员账号" : "个人账号"}</p></div><Button loading={busy} onClick={async()=>{if(busy)return;setBusy(true);setError("");try{await logout();clearBrowserDrafts();notifyAccountChanged();}catch(e){setError(e instanceof Error?e.message:"退出登录失败，请重试。");}finally{setBusy(false);}}}>退出登录</Button></div>
        <section className="atlas-account-section"><h3>修改密码</h3><PasswordChangeForm onChanged={()=>{clearBrowserDrafts();notifyAccountChanged(undefined,"密码已修改，全部会话已退出，请重新登录。",true);}}/></section>
        <AccountServices signedIn/>
      </> : <>
        <p>现在使用本机工作空间。登录后拥有独立的论文库、笔记和学习记录，现有本机资料继续保留。</p>
        {session ? <AuthenticationForm registrationEnabled={session.registration_enabled} emailRecoveryEnabled={session.recovery_email_enabled} onAuthenticated={value=>{setSession(value);notifyAccountChanged(value);}}/> : <p role="status">正在加载账号服务…</p>}
        <AccountServices signedIn={false}/>
      </>}
    </section>}
    {tab==="notebook"&&<Notebook/>}{tab!=="account"&&tab!=="notebook"&&<div className="settings-save"><span role="status">{dirty?"有未保存的修改":"设置已保存"}</span><Button type="primary" loading={busy||loading} disabled={!dirty} onClick={()=>void save()}>保存设置</Button></div>}
   </div></div></div>;
}

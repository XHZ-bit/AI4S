import "./CaseStudy.css";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Col, Collapse, Input, Radio, Row, Select, Space, Spin, Steps, Tag, Typography } from "antd";
import { apiGet } from "../api/client";
import { answerCaseQuestion, caseBase, getCase, getCaseSession, importCaseRun, newCaseSession, patchCaseSession } from "../api/cases";
import type { CaseInfo, CaseSession, Profile } from "../api/cases";
import InteractiveLab from "../components/workspace/InteractiveLab";
import SourceView from "../components/workspace/SourceView";
import { useInspector } from "../components/workspace/InspectorContext";

const storageKey = (id:string) => `atlas:case:${id}`;
function remember(id:string,sid:string) { try { localStorage.setItem(storageKey(id),sid); } catch { /* URL still preserves progress */ } }
function remembered(id:string) { try { return localStorage.getItem(storageKey(id)); } catch { return null; } }

export default function CaseStudy() {
  const { caseId = "diffusion-policy-intro" } = useParams();
  const [params,setParams] = useSearchParams();
  const inspector = useInspector();
  const sid = params.get("session");
  const [info,setInfo] = useState<CaseInfo>();
  const [session,setSession] = useState<CaseSession>();
  const [history,setHistory] = useState<{id:string; updated_at:string; case_version:string}[]>([]);
  const [profile,setProfile] = useState<Profile>();
  const [choices,setChoices] = useState<Record<string,number>>({});
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(true);
  const lock = useRef(false);
  const generation = useRef(0);
  const address = useRef("");
  address.current = `${caseId}/${sid || ""}`;

  useEffect(() => {
    const abort = new AbortController();
    const current = ++generation.current;
    setLoading(true); setError(""); setSession(undefined); setChoices({}); setProfile(undefined);
    Promise.all([getCase(caseId,abort.signal),apiGet<{items:typeof history}>(`${caseBase(caseId)}/sessions`,undefined,abort.signal)])
      .then(async ([data,sessions]) => {
        if (generation.current !== current) return;
        setInfo(data); setHistory(sessions.items);
        const selected = sid || remembered(caseId) || sessions.items[0]?.id;
        if (selected) {
          const saved = await getCaseSession(caseId,selected,abort.signal);
          if (generation.current !== current) return;
          setSession(saved); setProfile(saved.state.profile);
          setChoices(Object.fromEntries(Object.entries(saved.state.answers).map(([id,a])=>[id,a.choice])));
          remember(caseId,saved.id);
        }
      }).catch(e => { if (e.name !== "AbortError" && generation.current === current) setError(String(e)); })
      .finally(() => { if (generation.current === current) setLoading(false); });
    return () => { abort.abort(); generation.current++; };
  },[caseId,sid]);

  async function mutate(work:()=>Promise<CaseSession>,message:string) {
    if (lock.current) return;
    lock.current=true; setBusy(true); setError(""); setNotice("");
    const target=address.current;
    try {
      const saved=await work();
      if (address.current !== target) return;
      setSession(saved); remember(caseId,saved.id); setNotice(message); inspector.refresh();
    } catch(e) { if(address.current===target) setError(String(e)); }
    finally { lock.current=false; setBusy(false); }
  }
  async function create() {
    if(lock.current)return;
    lock.current=true; setBusy(true); setError("");
    const target=address.current;
    try { const saved=await newCaseSession(caseId); if(address.current!==target)return; remember(caseId,saved.id); setLoading(true); setParams(old=>{const n=new URLSearchParams(old);n.set("session",saved.id);return n;}); }
    catch(e){setError(String(e));} finally{lock.current=false;setBusy(false);}
  }
  async function reload() {
    if(!session)return;
    await mutate(()=>getCaseSession(caseId,session.id),"已重新加载保存记录；未保存的选择仍保留，请重新提交。");
  }
  async function upload(file?:File) {
    if(!file||!session)return;
    const target=address.current;
    if(file.size>1024*1024){setError("结果包超过 1 MiB，请选择检查工具生成的 JSON 摘要。");return;}
    try { const value=JSON.parse(await file.text()); if(address.current!==target)return; await mutate(()=>importCaseRun(caseId,session.id,value),"检查记录已保存；不代表模型复现成功。"); }
    catch { setError("无法读取 JSON，请选择检查工具生成的原始结果文件。"); }
  }
  if(loading)return <Spin aria-label="加载专题"/>;
  if(!info)return <Alert type="error" message={error||"专题不可用"} action={<Link to="/">返回首页</Link>}/>;
  const index=Math.max(0,info.steps.findIndex(s=>s.id===(info.steps.some(s=>s.id===params.get("focus"))?params.get("focus"):session?.state.current_step)));
  const step=info.steps[index];
  const sourceIndices=step.id==="interface"?[0]:step.id==="config"?[1]:step.id==="reflect"?[2]:[0,1,2];
  const latest=session?.runs[0];
  const base=caseBase(caseId);
  const questions=info.questions.filter(q=>q.step===step.id);
  const wrong=Object.entries(session?.state.answers||{}).filter(([,a])=>!a.correct);
  function stepComplete(id:string) {
    if(!session)return false;
    const answers=session.state.answers;
    if(id==="orient")return session.state.read_steps.includes(id);
    if(id==="interface")return !!answers.interface?.correct&&!!answers.horizon?.correct;
    if(id==="config")return !!answers.configuration?.correct;
    if(id==="inspect")return !!latest?.report.passed;
    if(id==="reflect")return !!answers.scope?.correct&&!!latest?.report.passed;
    return false;
  }
  const changeStep=(next:number)=>{setParams(old=>{const n=new URLSearchParams(old);n.set("focus",info.steps[next].id);return n;});return session&&mutate(()=>patchCaseSession(caseId,session.id,{version:session.version,current_step:info.steps[next].id}),"步骤已保存，可随时继续。");};

  return <Space className="case-study" data-session-id={session?.id} direction="vertical" size="large" style={{width:"100%"}}>
    <div><Link to="/">← 返回首页</Link><Typography.Title level={2}>{info.title}</Typography.Title>
      <Space wrap><Tag color="blue">免模型 API · 源码入门</Tag><Tag>专题 v{info.version}</Tag><Tag>{info.status}</Tag></Space>
    </div>
    <Alert type="info" showIcon message="这次会学到什么" description={info.notice}/>
    {error&&<Alert role="alert" type="error" showIcon message={error} description="保存记录仍保留。并发冲突时请重新加载，再提交当前操作。" action={session?<Button onClick={reload} disabled={busy}>重新加载记录</Button>:undefined}/>}
    {notice&&<Alert type="success" message={notice} closable onClose={()=>setNotice("")}/>}
    <Space wrap>
      <Button onClick={create} loading={busy} type={session?"default":"primary"}>{session?"新建独立学习记录":"开始学习并保存进度"}</Button>
      {history.length>0&&<Select aria-label="历史学习记录" placeholder="恢复其他记录" style={{minWidth:240}} value={session?.id} disabled={busy} onChange={id=>{setLoading(true);setParams(old=>{const n=new URLSearchParams(old);n.set("session",id);return n;});}} options={history.map(h=>({value:h.id,label:h.updated_at+" UTC · "+h.id.slice(0,8)}))}/>}
      {session&&<a href={base+"/sessions/"+session.id+"/report"} download>导出学习与检查报告</a>}
    </Space>
    {!session&&<Card title="先了解流程"><p>读懂接口 → 核对配置 → 本机检查 → 解释结果。无需上传论文，也不会自动运行模型。</p><p>预计阅读与源码检查约 25 分钟；这是教学估计，不是实测学习成效。</p></Card>}
    <InteractiveLab caseId={caseId} session={session} onSaved={saved=>{setSession(previous=>previous?.id===saved.id&&saved.version>=previous.version?saved:previous);}} />
    {session&&<>
      {session.stale&&<Alert type="warning" message="专题版本已变化，请新建记录继续；历史内容仍可导出。"/>}
      <Steps current={index} direction="horizontal" responsive onChange={n=>!busy&&!session.stale&&changeStep(n)} items={info.steps.map(s=>({title:s.title,status:s.id===step.id?("process" as const):stepComplete(s.id)?("finish" as const):("wait" as const)}))}/>
      {wrong.length>0&&<Alert type="warning" message="有理解问题需要回顾" description={<Space wrap>{wrong.map(([id,a])=><Button key={id} disabled={busy||session.stale} onClick={()=>changeStep(info.steps.findIndex(s=>s.id===a.review_step))}>{info.questions.find(q=>q.id===id)?.question}</Button>)}</Space>}/>}
      <Row gutter={[20,20]}>
        <Col xs={24} lg={14}><Space direction="vertical" size="middle" style={{width:"100%"}}>
          <Card title={step.title} extra={<Tag>约 {step.minutes} 分钟</Tag>}>
            <p>{step.body}</p><Typography.Text strong>完成标准：{step.criterion}</Typography.Text>
            {step.id==="orient"&&profile&&<Space direction="vertical" style={{width:"100%",marginTop:16}}>
              <label>本次目标<Input value={profile.goal} maxLength={300} onChange={e=>setProfile({...profile,goal:e.target.value})}/></label>
              <label>操作系统<Input value={profile.system} maxLength={100} onChange={e=>setProfile({...profile,system:e.target.value})}/></label>
              <label>可用算力<Input value={profile.compute} maxLength={100} onChange={e=>setProfile({...profile,compute:e.target.value})}/></label>
              <Button disabled={busy||session.stale} onClick={()=>mutate(()=>patchCaseSession(caseId,session.id,{version:session.version,profile}),"学习目标已保存。")}>保存目标</Button>
            </Space>}
            {step.id==="inspect"&&<Space direction="vertical" style={{width:"100%",marginTop:16}}>
              <p>1. 下载检查工具与离线源码包，放在同一文件夹。解压源码包为 atlas-sources 文件夹。</p>
              <Space wrap><a href={base+"/checker"} download>下载 Python 检查工具</a><a href={base+"/sources.zip"} download>下载离线源码包（含原许可）</a></Space>
              <p>2. 在该文件夹打开终端，执行以下命令。无需安装 PyTorch，也不会运行模型。</p>
              <Typography.Paragraph copyable code style={{overflowWrap:"anywhere"}}>python atlas_case_check.py --source-dir atlas-sources --output atlas-result.json</Typography.Paragraph>
              <p>输出文件已存在时更换文件名，以保留历史。去掉 --source-dir atlas-sources 可从固定官方地址在线读取源码。</p>
              <label>3. 导入结果 JSON<input aria-label="导入检查结果 JSON" type="file" accept=".json,application/json" disabled={busy||session.stale} onChange={e=>{void upload(e.target.files?.[0]);e.target.value="";}} style={{display:"block",marginTop:8}}/></label>
            </Space>}
            <Space wrap style={{marginTop:20}}>
              <Button disabled={busy||session.stale} onClick={()=>mutate(()=>patchCaseSession(caseId,session.id,{version:session.version,read_step:step.id}),"已记录读过；不代表理解检查或实验已通过。")}>{session.state.read_steps.includes(step.id)?"已记录阅读":"标记读过"}</Button>
              {index>0&&<Button disabled={busy||session.stale} onClick={()=>changeStep(index-1)}>上一步</Button>}
              {index<info.steps.length-1&&<Button type="primary" disabled={busy||session.stale} onClick={()=>changeStep(index+1)}>下一步</Button>}
            </Space>
          </Card>
          {questions.map(q=>{const a=session.state.answers[q.id];return <Card key={q.id} title="理解检查">
            <Typography.Paragraph strong>{q.question}</Typography.Paragraph>
            <Radio.Group value={choices[q.id]} onChange={e=>setChoices({...choices,[q.id]:e.target.value})}><Space direction="vertical">{q.options.map((option,n)=><Radio key={n} value={n}>{option}</Radio>)}</Space></Radio.Group>
            <div style={{marginTop:16}}><Button disabled={choices[q.id]===undefined||busy||session.stale} onClick={()=>mutate(()=>answerCaseQuestion(caseId,session.id,{version:session.version,question_id:q.id,choice:choices[q.id]}),"回答已保存，反馈不等于全面掌握评估。")}>检查回答</Button></div>
            {a&&<Alert style={{marginTop:12}} type={a.correct?"success":"warning"} message={a.correct?"本题回答正确":"建议回顾对应源码"} description={a.explanation}/>}
          </Card>})}
          {latest&&<Card title="最新导入的源码检查">
            <Alert type={latest.report.passed?"success":"warning"} message={latest.report.passed?"记录一致性检查通过":"检查记录有待处理项"} description={latest.report.verification}/>
            <p>{latest.report.notice}</p><Space wrap>{latest.report.checks.map(c=><Tag key={c.id} color={c.passed?"green":"red"}>{c.label}：{c.passed?"通过":"未通过"}</Tag>)}</Space>
          </Card>}
        </Space></Col>
        <Col xs={24} lg={10}><Space direction="vertical" size="middle" style={{width:"100%"}}>
          <Card title="依据与代码对照"><p><a href={info.paper_url} target="_blank" rel="noreferrer">阅读论文原文入口</a></p><p>{info.paper_notice}</p><Typography.Paragraph copyable>{info.commit}</Typography.Paragraph>
            {info.mappings.filter(m=>sourceIndices.includes(m.source)).map(m=><div key={m.title} style={{marginTop:14}}><Button type="link" onClick={()=>inspector.inspect({kind:"source",id:info.sources[m.source].path,line:m.line})}>{m.title} · 第 {m.line} 行</Button><p>{m.explanation}</p></div>)}
            <Collapse items={info.sources.filter((_,n)=>sourceIndices.includes(n)).map(s=>({key:s.path,label:s.path,children:<SourceView text={s.text} />}))}/>
            <p style={{marginTop:12}}>源码版权：Columbia Artificial Intelligence and Robotics Lab，MIT；离线包保留原许可。教学说明为平台整理，尚待领域评估。</p>
          </Card>
          <Card title="我卡住了"><Collapse items={info.troubleshooting.map(t=>({key:t.id,label:t.title,children:<p>{t.action}</p>}))}/></Card>
          <Card title="学习记录"><p>理解检查已作答 {Object.keys(session.state.answers).length}/{info.questions.length}；读过 {session.state.read_steps.length}/{info.steps.length} 步。均不代表完成模型复现。</p><p>共保存 {session.runs.length} 次不同检查记录。</p>
            <Collapse items={session.runs.slice(1).map(r=>({key:r.id,label:r.created_at+" UTC · "+(r.report.passed?"一致性通过":"需处理"),children:<p>{r.report.notice}</p>}))}/>
          </Card>
        </Space></Col>
      </Row>
    </>}
  </Space>;
}

import {useEffect,useRef,useState} from 'react';
import {Link,useNavigate,useSearchParams} from 'react-router-dom';
import {Alert,Button,Form,Input,Select,Space,Spin,Tag,Typography,message} from 'antd';
import type {DomainId,ProjectStage,ResearchProject,ResearchProjectCreate} from '../../api/project-types';
import {PROJECT_STAGES,projectDomainLabel} from '../../api/project-types';
import {createProject,listProjects} from '../../api/projects';
import {saveKnowledgePreferences} from '../../api/knowledge';
import type {WorkspaceMode} from '../../api/knowledge';
import TopicExplorer from '../../components/workbench/TopicExplorer';
import ResearchDomainInput,{parseResearchDomain} from '../../components/research/ResearchDomainInput';
import './research-workspace.css';
import './research-projects.css';

type CreateValues={title:string;research_question?:string;domain:DomainId;domain_input?:string;custom_domain?:string;objective?:string;required_metrics?:string[];notes?:string};
const starts:{stage:ProjectStage;title:string;description:string}[]=[{stage:'exploring',title:'还在找方向',description:'先收集兴趣和资料，问题与目标可以稍后再定。'},{stage:'framing',title:'有一个大致想法',description:'把想法拆成可以查阅和比较的小问题。'},{stage:'validating',title:'已有明确问题',description:'填写验证目标，准备比较条件和实验方案。'}];
export default function ResearchProjectsPage(){
 const navigate=useNavigate();const [params,setParams]=useSearchParams();const [items,setItems]=useState<ResearchProject[]>([]),[loading,setLoading]=useState(true),[creating,setCreating]=useState(false),[open,setOpen]=useState(params.get("new")==="1"),[error,setError]=useState(''),[createError,setCreateError]=useState('');
 const [mode,setMode]=useState<WorkspaceMode>('explore');const [details,setDetails]=useState(false);const [stage,setStage]=useState<ProjectStage>('exploring'),[showExplore,setShowExplore]=useState(false),[brief,setBrief]=useState('');const [form]=Form.useForm<CreateValues>();const createLock=useRef(false);
 const reload=async(signal?:AbortSignal)=>{setLoading(true);setError('');try{setItems((await listProjects({limit:100},signal)).items)}catch(e){if(!signal?.aborted)setError(e instanceof Error?e.message:'课题加载失败')}finally{if(!signal?.aborted)setLoading(false)}};
 useEffect(()=>{const c=new AbortController();void reload(c.signal);return()=>c.abort()},[]);
 const begin=()=>{setCreateError('');setOpen(true);setParams(old=>{const n=new URLSearchParams(old);n.set('new','1');return n})};
 const close=()=>{if(creating)return;setOpen(false);setParams(old=>{const n=new URLSearchParams(old);n.delete('new');return n})};
 const submit=async(v:CreateValues)=>{if(createLock.current)return;createLock.current=true;setCreating(true);setCreateError('');const body:ResearchProjectCreate={title:v.title,research_question:v.research_question?.trim()||'',...parseResearchDomain(v.domain_input),stage,constraints:{version:1,objective:v.objective?.trim()||'',allowed_datasets:[],excluded_datasets:[],required_metrics:v.required_metrics||[],compute:[],time_budget:null,cost_budget:null,data_access:[],notes:[...(v.notes||'').split('\n').map(x=>x.trim()).filter(Boolean),...(brief?['探索起点（用户选择，可修改）：'+brief]:[])]}};
  try{const created=await createProject(body);try{await saveKnowledgePreferences(created.id,{mode})}catch{message.warning('空间已建立，使用方式可在空间内重新选择')}message.success(stage==='exploring'?'探索空间已建立':'课题已建立');setOpen(false);form.resetFields();setBrief('');navigate(`/research/${created.id}?view=graph`)}catch(e){setCreateError(e instanceof Error?e.message:'课题创建失败')}finally{createLock.current=false;setCreating(false)}};
 return <div className="ps-projects-page"><header className="research-page-heading"><div><h1>研究空间</h1><p className="project-create-intro">围绕一个方向，收拢资料、问题和成果。</p></div>{!open&&(items.length>0||!!error)&&<Button type="primary" onClick={begin}>建立课题</Button>}</header>
 {error&&<Alert type="error" showIcon message="空间列表暂不可用" description={error} action={<Button onClick={()=>void reload()}>重试</Button>}/>}
 {open&&<section className="ps-create-space" aria-label="建立科研课题"><header><h2>先给这次探索起个名字</h2><Button type="text" onClick={close} disabled={creating}>收起</Button></header><p>可以是暂定名称。进入空间后，再逐步明确问题和研究条件。</p>
 {createError&&<Alert type="error" showIcon message="尚未建立，请检查填写内容" description={createError}/>}
 <Form form={form} layout="vertical" onFinish={submit} initialValues={{domain:'custom'}}>
  <Form.Item name="title" label="课题名称" rules={[{required:true,whitespace:true,message:'先给这个研究空间起个名字'}]}><Input autoFocus maxLength={300} placeholder="例如：我对人机协作的探索"/></Form.Item>
  <Form.Item label="本空间使用方式"><Select aria-label="新空间使用方式" value={mode} onChange={setMode} options={[{value:'explore',label:'零基础探索'},{value:'research',label:'已有思路深入研究'},{value:'reproduce',label:'阅读与复现'}]}/><p className="kw-muted">决定讲解深度和推荐内容，进入空间后可以随时调整。</p></Form.Item>
  <details open={details} onToggle={event=>setDetails(event.currentTarget.open)}><summary>已有想法？补充领域、问题和目标</summary><div className="ps-create-details">
   <div className="project-start-options" aria-label="研究准备阶段">{starts.map(s=><button key={s.stage} type="button" aria-pressed={stage===s.stage} onClick={()=>setStage(s.stage)}><strong>{s.title}</strong><span>{s.description}</span></button>)}</div>
   <Form.Item name="domain_input" label="研究领域"><ResearchDomainInput/></Form.Item>
   {stage!=='validating'&&<section><Button type="link" onClick={()=>setShowExplore(v=>!v)}>{showExplore?'收起选题探索':'还没思路，帮我找一个起点'}</Button>{showExplore&&<TopicExplorer onChoose={(d,b)=>{form.setFieldValue('research_question',d.question);setBrief(JSON.stringify(b));setStage('framing');message.info('已填入暂拟问题，你可以继续改写')}}/>}</section>}
   <Form.Item name="research_question" label="研究问题" rules={stage==='validating'?[{required:true,whitespace:true,message:'验证阶段需要明确问题；也可以先选择探索阶段'}]:[]}><Input.TextArea rows={3} maxLength={4000} placeholder="你现在好奇什么？暂时不确定也没关系"/></Form.Item>
   <Form.Item name="objective" label={stage==='validating'?'首轮验证目标':'当前想做的事'} rules={stage==='validating'?[{required:true,whitespace:true,message:'填写验证目标，或返回探索阶段'}]:[]}><Input.TextArea rows={2} maxLength={4000} placeholder="例如：先看懂几篇论文，比较两类方法"/></Form.Item>
   <details><summary>指标、资源和其他条件</summary><Form.Item name="required_metrics" label="预期关注指标"><Select mode="tags" tokenSeparators={[',','，']} placeholder="未确定可暂不填写"/></Form.Item><Form.Item name="notes" label="已知条件与待确认事项"><Input.TextArea rows={3} placeholder="每行一项；暂时没有也可留空"/></Form.Item></details>
  </div></details>
  <Space className="ps-create-submit"><Button type="primary" htmlType="submit" loading={creating}>{stage==='exploring'?'建立探索空间':'建立课题'}</Button><Button onClick={close} disabled={creating}>取消</Button></Space>
 </Form></section>}
 {!open&&(loading?<Spin/>:items.length===0?<section className="research-projects-empty"><h3>还没有课题</h3><p>从一个兴趣或一篇论文开始，问题可以慢慢想清楚。</p><Button type="primary" onClick={begin}>建立第一个课题</Button></section>:<ul className="ps-space-list">{items.map(p=><li key={p.id}><Link to={'/research/'+p.id}><div><h2>{p.title}</h2><p>{p.research_question||'研究问题尚未确定，继续探索兴趣和资料。'}</p><span>{projectDomainLabel(p)}</span></div><span>{p.status==='archived'?'已归档':PROJECT_STAGES[p.stage||'validating']}</span></Link></li>)}</ul>)}
 </div>;
}

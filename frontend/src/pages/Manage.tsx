import ImportBar from "../components/workbench/ImportBar";
import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import { Alert, Button, Checkbox, Form, Input, InputNumber, message, Segmented } from "antd";
import { ClockCircleOutlined, DownOutlined, InfoCircleOutlined } from "@ant-design/icons";
import { Link, useSearchParams, useLocation } from "react-router-dom";
import { collect } from "../api/papers";
import PaperSearchPanel from "../components/PaperSearchPanel";
import PaperLibrary from "../components/PaperLibrary";
import UploadLimits from "../components/UploadLimits";
import { useAccessMode } from "../components/SessionContext";
import PdfUploadQueue from "../components/PdfUploadQueue";
import "./manage.css";

export default function Manage() {
  const [params,setParams]=useSearchParams();
  const {hash}=useLocation();
  const projectId=params.get("project")||undefined;
  const view=params.get("view")|| (params.get("add")==="1"||hash.includes("import")?"add":params.has("q")?"discover":"library");
  const selectView=(value:string)=>setParams(old=>{const n=new URLSearchParams(old);n.set("view",value);return n;});
  const multiuser = useAccessMode() === "multiuser";
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0), [collectionOpen, setCollectionOpen] = useState(false);
  const [maxFileBytes, setMaxFileBytes] = useState<number>();
  const [collectionForm] = Form.useForm();
  const [project,setProject]=useState<{id:string;title:string;papers:string[]}>(),[projectError,setProjectError]=useState("");
  useEffect(()=>{if(!projectId){setProject(undefined);return;}const c=new AbortController();setProjectError("");apiGet<any>(`/api/workbench/projects/${encodeURIComponent(projectId)}`,undefined,c.signal).then(r=>{if(!c.signal.aborted)setProject({id:projectId,title:r.project.title,papers:(r.papers||[]).map((p:any)=>p.uid)})}).catch(e=>{if(!c.signal.aborted)setProjectError(String(e))});return()=>c.abort()},[projectId,refresh]);
  const currentProject=project?.id===projectId?project:undefined;
  const changed=()=>setRefresh(v=>v+1);

  return <div className="atlas-manage">
    <header className="atlas-manage-heading">
      <div><h1>论文库</h1>{projectId&&<div className="atlas-manage-project"><Link to={`/research/${encodeURIComponent(projectId)}?tab=reading`}>← 返回当前研究空间</Link><span>{currentProject?.title||"当前研究空间"} · 添加后可在空间内继续阅读</span></div>}</div>
      <div className="atlas-manage-shortcuts"><Button type="primary" onClick={()=>selectView("add")}>添加论文</Button><Link to="/workflow?view=processing"><ClockCircleOutlined aria-hidden />系统处理</Link></div>
    </header>
    <Segmented aria-label="资料库视图" value={view} onChange={v=>selectView(String(v))} options={[{value:"library",label:"我的论文"},{value:"add",label:"添加资料"},{value:"discover",label:"检索与发现"}]}/>
    {projectError&&<Alert type="error" message="无法读取研究空间资料" description={projectError} action={<Button onClick={changed}>重试</Button>}/>}
    {error && <Alert closable onClose={() => setError("")} type="error" showIcon message={error} />}
    {view==="library"&&<PaperLibrary key={projectId||"personal"} refreshVersion={refresh} projectId={projectId} projectPaperUids={currentProject?.papers} onProjectChange={changed} />}
    {view==="add"&&<>
    <section className="atlas-manage-import" aria-labelledby="atlas-manage-import-title">
      <div className="atlas-manage-import-heading"><h2 id="atlas-manage-import-title">添加论文</h2></div>
      {projectId&&<div className="atlas-manage-existing"><span>论文已经在你的资料库中？</span><Button onClick={()=>selectView("library")}>从资料库选择</Button></div>}
      <ImportBar key={projectId||"personal"} onDone={changed}/><div className="atlas-manage-upload"><PdfUploadQueue key={projectId||"personal"} projectId={projectId} maxFileBytes={maxFileBytes} onLibraryChange={() => setRefresh(value => value + 1)} /></div>
      {multiuser && <div className="atlas-manage-upload-limits"><UploadLimits onMaxBytes={setMaxFileBytes} /></div>}
    </section>
    </>}
    {view==="discover"&&<>
    <div className="atlas-manage-search"><PaperSearchPanel /></div>
    {multiuser ? <p className="atlas-manage-collection-note"><InfoCircleOutlined aria-hidden /><span>多人试用暂未开放联网采集，请上传 PDF 添加到自己的论文库。</span></p> : <section className="atlas-manage-collection">
      <button className="atlas-manage-collection-toggle" type="button" aria-expanded={collectionOpen} aria-controls="atlas-arxiv-form" onClick={() => setCollectionOpen(value => !value)}>
        <span>从 arXiv 采集</span><DownOutlined aria-hidden className={collectionOpen ? "is-open" : ""} />
      </button>
      {collectionOpen && <div id="atlas-arxiv-form" className="atlas-manage-collection-body">
        <Form form={collectionForm} layout="vertical" className="atlas-manage-collection-form" initialValues={{ keywords: "diffusion policy", categories: "cs.RO", start_year: 2023, max_results: 20 }}
          onFinish={async values => {
            if (multiuser) return;
            setBusy(true);
            try {
              await collect({ ...values, keywords: values.keywords.split(/[,，]/).map((value: string) => value.trim()).filter(Boolean), categories: values.categories.split(/[,，]/).map((value: string) => value.trim()).filter(Boolean) });
              message.success("采集已提交，请在处理进度查看");
            } catch (caught) { setError(String(caught)); }
            finally { setBusy(false); }
          }}>
          <Form.Item name="keywords" label="关键词" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="categories" label="分类" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="start_year" label="起始年份"><InputNumber min={1900} max={2100} /></Form.Item>
          <Form.Item name="max_results" label="数量"><InputNumber min={1} max={100} /></Form.Item>
          <Button htmlType="submit" loading={busy}>采集</Button>
          <Form.Item className="atlas-collection-extra" name="include_citations" valuePropName="checked"><Checkbox>同时补充外部引用（耗时更长）</Checkbox></Form.Item>
        </Form>
        <p>本地解析无需模型。配置模型后可主动提交候选抽取。</p>
      </div>}
    </section>}
    </>}
  </div>;
}

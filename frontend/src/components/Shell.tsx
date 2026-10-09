import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ApartmentOutlined, BookOutlined, CompassOutlined, ExperimentOutlined, HomeOutlined, NodeIndexOutlined, SettingOutlined, ThunderboltOutlined } from "@ant-design/icons";
import Workspace from "./workspace/Workspace";
import WorkflowSummary from "./WorkflowSummary";
import type { Scope } from "../api/assistant";
import "./workspace/workspace.css";
const links = [
 {path:"/",title:"开始 / 继续",icon:<HomeOutlined/>}, {path:"/research",title:"科研课题",icon:<ApartmentOutlined/>},
 {path:"/manage",title:"论文库",icon:<BookOutlined/>}, {path:"/cases/diffusion-policy-intro",title:"专题实践",icon:<ExperimentOutlined/>},
 {path:"/roadmap",title:"学习路线",icon:<CompassOutlined/>}, {path:"/workflow",title:"统一任务",icon:<ThunderboltOutlined/>}, {path:"/demo/personalized-roadmap",title:"个性化路线案例",icon:<CompassOutlined/>}, {path:"/graph",title:"探索知识",icon:<NodeIndexOutlined/>}, {path:"/tasks",title:"处理进度",icon:<ThunderboltOutlined/>}
];
export default function Shell({children}:{children:ReactNode}) {
 const {pathname}=useLocation(); const parts=pathname.split("/");
 const scope:Scope|null=parts[1]==="research"&&parts[2]?"project":parts[1]==="papers"&&parts[2]?"paper":parts[1]==="cases"&&parts[2]?"case":null;
 const id=parts[2]?decodeURIComponent(parts[2]):"";
 useEffect(()=>{document.title="Research Atlas · 让研究的下一步看得见";},[]);
 return <div className="atlas-shell"><aside className="atlas-sidebar"><Link className="atlas-brand" to="/"><span className="atlas-brand-symbol">A<span>•</span></span><div>Research Atlas<small>连接理解与研究行动</small></div></Link><span className="atlas-nav-caption">WORKSPACE</span><nav aria-label="主导航">{links.map(link=><Link className={(link.path==="/"?pathname==="/":pathname.startsWith(link.path))?"active":""} key={link.path} to={link.path} title={link.title}>{link.icon}<span>{link.title}</span></Link>)}</nav><div className="atlas-sidebar-bottom"><span className="atlas-local-status"><i/>本地优先 · 上下文可追溯</span><Link to="/admin/quality"><SettingOutlined/><span>维护者工作台</span></Link></div></aside><div className="atlas-body"><header className="atlas-global-header"><span>你的科研工作空间</span><Link to="/tasks"><span className="atlas-status-dot"/>后台任务</Link></header><div className="atlas-content">{scope?<Workspace key={`${scope}:${id}`} scope={scope} id={id}><>{children}<WorkflowSummary kind={scope} id={id}/></></Workspace>:children}</div><footer className="atlas-footer">结论可追溯 · 学习可继续 · 实验可记录</footer></div></div>;
}

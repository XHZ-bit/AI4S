import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Avatar,Drawer } from "antd";
import {usePreferences} from "./PreferencesContext";
import { PlusOutlined, ApartmentOutlined, BookOutlined, ClockCircleOutlined, CompassOutlined, HomeOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MoonOutlined, MoreOutlined, SettingOutlined, SunOutlined, } from "@ant-design/icons";
import Workspace from "./workspace/Workspace";
import useRecentProjects from "./workbench/useRecentProjects";
import "./workbench/workspace-experience.css";
import QuickLauncher from "./QuickLauncher";
import type { Scope } from "../api/assistant";
import { useAccessMode,useCurrentAccount } from "./SessionContext";
import { useAtlasTheme } from "../theme";
import "./workspace/workspace.css";
import "./interface.css";
const links = [
 {path:"/",title:"工作台",short:"工作台",group:"工作空间",icon:<HomeOutlined/>},
 {path:"/graph",title:"知识图谱",short:"图谱",group:"工作空间",icon:<ApartmentOutlined/>},
 {path:"/manage",title:"资料库",short:"资料",group:"工作空间",icon:<BookOutlined/>},
 {path:"/explore",title:"探索",short:"探索",group:"工作空间",icon:<CompassOutlined/>},
 {path:"/settings",title:"设置",short:"设置",group:"工作空间",icon:<SettingOutlined/>}
];

function BrandMark() {
 return <span className="atlas-brand-symbol" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M10 26V6h8a7 7 0 0 1 0 14h-8" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/></svg></span>;
}

export default function Shell({children}:{children:ReactNode}) {
 const {pathname}=useLocation(); const parts=pathname.split("/");
 const mode=useAccessMode();const account=useCurrentAccount();const recent=useRecentProjects();
 const {preferences}=usePreferences();
 const learning=preferences.features.foundations||preferences.features.quizzes||preferences.features.coding||preferences.features.paper_guidance;
 const visibleLinks=links.filter(link=>link.path==="/graph"?preferences.features.graph:link.path==="/roadmap"||link.path==="/demo/personalized-roadmap"?preferences.features.roadmap:link.path==="/learn"||link.path.startsWith("/cases/")?learning:true);
 const { mode: visualMode, toggle: toggleVisualMode } = useAtlasTheme();
 const [mobile,setMobile]=useState(()=>window.matchMedia("(max-width: 767px)").matches);
 const [collapsed,setCollapsed]=useState(()=>{try{const saved=localStorage.getItem("atlas:sidebar-collapsed");return saved===null?window.innerWidth<1280:saved==="true";}catch{return window.innerWidth<1280;}});
 const toggleSidebar=()=>setCollapsed(previous=>{const next=!previous;try{localStorage.setItem("atlas:sidebar-collapsed",String(next));}catch{}return next;});
 const [more,setMore]=useState(false);
 const launcherHandoff=useRef(false);
 useEffect(()=>{const query=window.matchMedia("(max-width: 767px)");const update=()=>{setMobile(query.matches);setMore(false);};query.addEventListener("change",update);return()=>query.removeEventListener("change",update);},[]);
 useEffect(()=>{setMore(false);},[pathname]);
 useEffect(()=>{const close=()=>{launcherHandoff.current=true;setMore(false);};window.addEventListener("atlas:close-navigation",close);return()=>window.removeEventListener("atlas:close-navigation",close);},[]);
 const scope:Scope|null=parts[1]==="research"&&parts[2]?"project":parts[1]==="papers"&&parts[2]?"paper":parts[1]==="cases"&&parts[2]?"case":null;
 const id=parts[2]?decodeURIComponent(parts[2]):"";
 const active=(path:string)=>path==="/"?pathname==="/":pathname===path||pathname.startsWith(`${path}/`);
 const current=pathname==="/settings"?"个人设置":scope==="paper"?"论文阅读":scope==="project"?"课题工作台":links.find(link=>active(link.path))?.title||({"/research":"研究空间","/learn":"专注学习","/practice":"专题实践","/workflow":"任务面板","/tasks":"系统处理","/actions":"我的行动","/roadmap":"学习路线"} as Record<string,string>)[pathname]||"研究工作空间";
 useEffect(()=>{document.title=`${current==="开始 / 继续"?"工作台":current} · PaperStride`;},[current]);
 const navigation=(items:typeof links,compact=false)=>items.map(link=><Link className={active(link.path)?"active":""} aria-current={active(link.path)?"page":undefined} aria-label={link.title} key={link.path} to={link.path} title={link.title} onClick={()=>setMore(false)}>{link.icon}<span>{compact?link.short:link.title}</span></Link>);
 return <div className={`atlas-shell atlas-interface ${collapsed?"sidebar-collapsed":"sidebar-expanded"}`}>
   <a className="atlas-skip-link" href="#atlas-main-content">跳到主要内容</a>
   {!mobile&&<aside className="atlas-sidebar"><Link className="atlas-brand" to="/" aria-label="PaperStride"><BrandMark/><div>PaperStride</div></Link><nav id="atlas-primary-navigation" aria-label="主导航">{["工作空间"].map(group=><div className="atlas-nav-group" key={group}><span className="atlas-nav-caption">{group}</span>{navigation(visibleLinks.filter(link=>link.group===group&&link.path!=="/settings"))}</div>)}</nav><nav className="ps-sidebar-spaces" aria-label="最近研究空间"><span className="atlas-nav-caption">研究空间</span>{recent.items.map(project=><Link key={project.id} to={`/research/${project.id}`} className={id===project.id?"active":""} title={project.title}><ApartmentOutlined aria-hidden="true"/><span>{project.title}</span></Link>)}<Link to="/research" aria-label="全部课题" title="全部课题"><PlusOutlined aria-hidden="true"/><span>全部课题</span></Link></nav><div className="atlas-sidebar-bottom"><Link to="/settings"><SettingOutlined aria-hidden="true"/><span>设置</span></Link><span className="atlas-local-status"><i/>{mode==="multiuser"||account?"个人空间":"本机空间"}</span>{(!account||account.role==="admin")&&<Link to="/admin/quality"><SettingOutlined aria-hidden="true"/><span>维护者工作台</span></Link>}</div></aside>}
   <div className="atlas-body"><header className="atlas-global-header">{!mobile&&<button type="button" className="atlas-sidebar-toggle" onClick={toggleSidebar} aria-label={collapsed?"展开功能栏":"收起功能栏"} aria-expanded={!collapsed} aria-controls="atlas-primary-navigation" title={collapsed?"展开功能栏":"收起功能栏"}>{collapsed?<MenuUnfoldOutlined/>:<MenuFoldOutlined/>}</button>}<div className="atlas-header-context"><strong>{current}</strong></div><QuickLauncher/><button type="button" className="atlas-theme-toggle" onClick={toggleVisualMode} aria-label={`切换到${visualMode==="dark"?"浅色":"深色"}主题`} title={`切换到${visualMode==="dark"?"浅色":"深色"}主题`}>{visualMode==="dark"?<SunOutlined aria-hidden="true"/>:<MoonOutlined aria-hidden="true"/>}<span>{visualMode==="dark"?"浅色":"深色"}</span></button><Link className={`atlas-account-entry ${account?"":"atlas-account-signin"}`} to="/settings?tab=account" aria-label={account?"个人设置":"登录 / 注册"} title={account?`${account.username} · 个人设置`:"登录 / 注册"}>{account?<Avatar size={30} src={preferences.avatar_url||undefined}>{preferences.profile.display_name?.slice(0,1)||account.username.slice(0,1)}</Avatar>:<span>登录 / 注册</span>}</Link><Link className="atlas-header-tasks" to="/workflow" aria-label="任务面板" title="任务面板"><ClockCircleOutlined aria-hidden="true"/><span>任务面板</span></Link></header><div id="atlas-main-content" tabIndex={-1} role={scope?undefined:"main"} className="atlas-content">{scope?<Workspace key={`${scope}:${id}`} scope={scope} id={id}>{children}</Workspace>:children}</div><footer className="atlas-footer"><span>PaperStride · 研究与阅读工作空间</span></footer></div>
   {mobile&&<nav className="atlas-mobile-navigation" aria-label="主导航">{navigation(visibleLinks.slice(0,4),true)}<button className={visibleLinks.slice(0,4).some(link=>active(link.path))?"":"active"} onClick={()=>{launcherHandoff.current=false;window.dispatchEvent(new Event("atlas:close-quick-launcher"));setMore(true);}} aria-label="更多页面" aria-expanded={more} aria-controls="atlas-more-navigation"><MoreOutlined aria-hidden="true"/><span>更多</span></button></nav>}
   {mobile&&<Drawer rootClassName="atlas-more-drawer" title="更多页面" placement="bottom" height="min(78dvh, 640px)" open={more} onClose={()=>setMore(false)} afterOpenChange={visible=>{if(!visible&&launcherHandoff.current){launcherHandoff.current=false;requestAnimationFrame(()=>window.dispatchEvent(new Event("atlas:focus-quick-launcher")));}}} destroyOnHidden><nav id="atlas-more-navigation" className="atlas-more-links" aria-label="更多页面">{navigation(visibleLinks.slice(4))}<Link to="/research" onClick={()=>setMore(false)}>全部课题</Link><Link to="/workflow" onClick={()=>setMore(false)}>任务与行动</Link><Link to="/settings" onClick={()=>setMore(false)}><SettingOutlined aria-hidden="true"/><span>个人设置</span></Link>{(!account||account.role==="admin")&&<Link to="/admin/quality" onClick={()=>setMore(false)}><SettingOutlined aria-hidden="true"/><span>维护者工作台</span></Link>}</nav></Drawer>}
 </div>;
}

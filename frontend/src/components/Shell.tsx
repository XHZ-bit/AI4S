import { Layout, Menu, Typography, Space, Tag } from "antd";
import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
export default function Shell({children}:{children:ReactNode}) {
 const {pathname}=useLocation();
 const selectedKey=pathname.startsWith("/research")?"/research":pathname;
 return <Layout style={{minHeight:"100vh",background:"#f3f6fa"}}>
 <Layout.Header style={{height:"auto",padding:"12px 24px",background:"#12263a"}}>
 <Space><Link to="/"><Typography.Text strong style={{color:"white",fontSize:22}}>Research Atlas</Typography.Text></Link><Tag color="cyan">科研学习工作台</Tag></Space>
 <Menu theme="dark" mode="horizontal" style={{background:"transparent",minWidth:0}} selectedKeys={[selectedKey]} items={[
 {key:"/",label:<Link to="/">开始 / 继续</Link>},{key:"/manage",label:<Link to="/manage">论文库</Link>},
 {key:"/research",label:<Link to="/research">科研课题</Link>},
 {key:"/cases/diffusion-policy-intro",label:<Link to="/cases/diffusion-policy-intro">专题实践</Link>},
 {key:"/roadmap",label:<Link to="/roadmap">学习路线</Link>},{key:"/graph",label:<Link to="/graph">探索知识</Link>},
 {key:"/tasks",label:<Link to="/tasks">处理进度</Link>}]}/>
 </Layout.Header><Layout.Content style={{padding:"24px clamp(12px, 3vw, 48px)",boxSizing:"border-box",minWidth:0,maxWidth:1500,width:"100%",margin:"0 auto"}}>{children}</Layout.Content>
 <Layout.Footer style={{textAlign:"center"}}>结论可追溯 · 学习可继续 · 实验可记录 <Link to="/admin/quality" style={{marginLeft:24}}>维护者工作台</Link></Layout.Footer>
 </Layout>;
}

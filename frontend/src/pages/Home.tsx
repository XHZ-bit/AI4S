import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Row, Space, Typography } from "antd";
import { Link } from "react-router-dom";
import { listPapers } from "../api/papers";
export default function Home(){
 const [papers,setPapers]=useState<any[]>([]); const [error,setError]=useState("");
 useEffect(()=>{listPapers(6).then(r=>setPapers(r.items)).catch(e=>setError(String(e)));},[]);
 return <Space direction="vertical" size="large" style={{width:"100%"}}>
 <div><Typography.Title>从读懂一篇论文，到迈出研究的下一步</Typography.Title>
 <Typography.Paragraph type="secondary">围绕同一篇目标论文，理解方法、准备复现、整理值得验证的问题。图谱和原文证据为每一步提供上下文。</Typography.Paragraph>
 <Space wrap><Link to="/cases/diffusion-policy-intro"><Button type="primary" size="large">体验源码入门案例</Button></Link><Link to="/manage"><Button size="large">选择或上传自己的论文</Button></Link></Space></div>
 <Row gutter={[16,16]}>{[["01 读懂论文","按章节阅读，查看有出处的解释，记录理解检查。"],["02 基础复现","记录环境、代码版本、实验配置与结果，区分跑通和复现。"],["03 研究方向","比较有证据的主张，把想法变成可验证的问题。"]].map(([title,text])=><Col xs={24} md={8} key={title}><Card title={title}>{text}</Card></Col>)}</Row>
 <Alert type="info" showIcon message="试点专题：Diffusion Policy" description="固定源码入门已开放；策略评估仍待实测。源码检查不代表模型或论文结果复现。"/>
 {error&&<Alert type="error" message={error}/>}
 <Typography.Title level={3}>继续学习</Typography.Title>
 <Row gutter={[16,16]}>{papers.map(p=><Col xs={24} md={12} key={p.uid}><Card title={p.title}><Space wrap><Link to={`/papers/${p.uid}?tab=reading`}>继续阅读</Link><Link to={`/papers/${p.uid}?tab=experiment`}>继续实验</Link><Link to={`/papers/${p.uid}?tab=research`}>研究问题</Link></Space></Card></Col>)}</Row>
 {!papers.length&&!error&&<Typography.Text type="secondary">还没有论文。先上传一篇 PDF，原文会先保存，再在后台解析。</Typography.Text>}
 </Space>;
}

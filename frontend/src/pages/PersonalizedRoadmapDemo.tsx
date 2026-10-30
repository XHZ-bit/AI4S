import { useState } from "react";
import { Button, Checkbox, Tabs } from "antd";
import { Link } from "react-router-dom";
import { CheckOutlined, DownloadOutlined } from "@ant-design/icons";
import { demoLearners, demoSources, routeModules, type Foundation } from "../data/personalized-roadmap-demo";
import "./personalized-roadmap-demo.css";

export default function PersonalizedRoadmapDemo() {
  const [learnerId, setLearnerId] = useState(demoLearners[0].id);
  const learner = demoLearners.find(item => item.id === learnerId)!;
  const [known, setKnown] = useState<Foundation[]>(learner.known);
  const modules = routeModules(known);
  const totalHours = modules.length * 6;
  const weeks = Math.ceil(totalHours / learner.weeklyHours);
  const modified = [...known].sort().join() !== [...learner.known].sort().join();
  function selectLearner(id: string) { setLearnerId(id); setKnown(demoLearners.find(item => item.id === id)!.known); }
  const report = `# ${learner.name}的学习报告（预设模拟案例）\n\n目标：${learner.goal}\n\n起点：${learner.background}\n\n约束：${learner.constraint}\n\n路线：${modules.map(module => module.title).join(" → ")}\n\n计划：${totalHours} 小时，每周 ${learner.weeklyHours} 小时，约 ${weeks} 周。\n\n${modules.map(module => `## ${module.title}\n\n${module.artifact}\n\n理解检查：${module.question}\n\n示例回答：${module.answer}`).join("\n\n")}\n\n## 学习反思\n\n${learner.reflection}\n\n## 下一步\n\n${learner.next}\n\n## 资料\n\n${Object.values(demoSources).map(source => `- [${source.title}](${source.url})`).join("\n")}\n\n以上是教学设计与模拟记录，不代表真实用户测评或论文实验复现。`;
  function downloadReport() {
    const url = URL.createObjectURL(new Blob([report], {type: "text/markdown;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = `paperstride-${learner.id}-demo.md`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="personalized-demo">
    <header className="demo-intro"><h1>同一个目标，三种学习起点</h1><p>以理解 Diffusion Policy 为例，看已有基础如何改变路线。画像、学习过程和产出均已预设，可直接查看。</p><span className="demo-simulation-label">预设案例 · 模拟学习记录</span></header>
    <nav className="demo-learner-picker" aria-label="示例学习者">{demoLearners.map(item => <button type="button" key={item.id} aria-pressed={item.id === learnerId} onClick={() => selectLearner(item.id)}><strong>{item.name}</strong><span>{item.role}</span></button>)}</nav>
    <div className="demo-case-layout">
      <div className="demo-case-main">
        <section className="demo-route-summary"><h2>{learner.name}的学习路线</h2><p>{modified ? "按你调整的基础重新裁剪，策略接口与验证模块始终保留。" : learner.rationale}</p><p className="demo-time-budget">{modules.length} 个阶段，共 {totalHours} 小时；每周 {learner.weeklyHours} 小时，约 {weeks} 周。时间为教学估计。</p></section>
        <Tabs items={[
          {key: "route", label: "完整学习路线", children: <div className="demo-modules">{modules.map((module, index) => <section key={module.id} className="demo-module">
            <header><span className="demo-stage-index">{index + 1}</span><div><h3>{module.title}</h3><span>计划第 {Math.floor(index * 6 / learner.weeklyHours) + 1} 周起 · 约 6 小时</span></div></header>
            <p>{module.purpose}</p><a href={demoSources[module.source].url} target="_blank" rel="noreferrer">阅读 {demoSources[module.source].short}</a>
            <ol className="demo-task-list">{module.tasks.map(task => <li key={task.title}><div><strong>{task.title}</strong><span>约 2 小时</span></div><p>{task.action}</p><p className="demo-task-output"><strong>产出：</strong>{task.output}</p></li>)}</ol>
            <details className="demo-checkpoint"><summary>理解检查与示例回答</summary><p><strong>{module.question}</strong></p><p>{module.answer}</p></details>
          </section>)}</div>},
          {key: "simulation", label: "模拟学习过程", children: <section className="demo-dialogue"><h3>学习者与指导者的三轮对话</h3><p>这些对话展示常见误解和反馈方式，是预设情境。</p>{learner.dialogue.map((turn, index) => <article key={turn.question}><h4>第 {index + 1} 轮</h4><p><strong>{learner.name}：</strong>{turn.question}</p><p className="demo-response"><strong>指导者：</strong>{turn.answer}</p></article>)}<h3>路线调整依据</h3><ul>{demoLearners.map(item=><li key={item.id}><strong>{item.role}：</strong>{item.rationale}</li>)}</ul></section>},
          {key: "report", label: "完整产出报告", children: <section className="demo-report"><header><h3>预设学习报告</h3><Button icon={<DownloadOutlined aria-hidden="true"/>} onClick={downloadReport}>导出完整案例</Button></header><p>示例中完成的是概念、接口与验证设计。以下内容为模拟产出，没有填写未经运行的实验指标。</p>{modules.map(module=><article key={module.id}><h4><CheckOutlined aria-hidden="true"/> {module.title}</h4><p>{module.artifact}</p></article>)}<article><h4>学习反思</h4><p>{learner.reflection}</p></article><article><h4>下一步行动</h4><p>{learner.next}</p></article></section>},
        ]}/>
        <footer className="demo-next"><Link to="/cases/diffusion-policy-intro">打开源码交互专题</Link><Link to="/roadmap">规划我自己的学习路线</Link></footer>
      </div>
      <aside className="demo-profile"><section><h2>学习画像</h2><p>{learner.background}</p><dl><dt>学习目标</dt><dd>{learner.goal}</dd><dt>时间与资源</dt><dd>{learner.constraint}</dd></dl><fieldset><legend>调整已有基础</legend><Checkbox.Group value={known} onChange={value => setKnown(value as Foundation[])} options={[{label: "了解模仿学习", value: "imitation"}, {label: "了解扩散模型", value: "diffusion"}]}/></fieldset>{modified&&<Button size="small" type="text" onClick={()=>setKnown(learner.known)}>恢复预设画像</Button>}</section>
        <section><h2>原始资料</h2>{Object.entries(demoSources).map(([id,source])=><article key={id}><a href={source.url} target="_blank" rel="noreferrer">{source.short}</a><p>{source.focus}</p></article>)}<details><summary>如何理解这个案例</summary><p>论文提供研究内容与实验依据；模块顺序、时间和对话为平台的教学设计。调整基础可观察路线变化，实际掌握仍需要你自己的回答与实践。</p></details></section>
      </aside>
    </div>
  </div>;
}

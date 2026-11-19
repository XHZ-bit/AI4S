import type {NodeStudyGuide as StudyGuide} from '../../api/knowledge';
import KnowledgeText from './KnowledgeText';
import './node-study-guide.css';

export default function NodeStudyGuide({guide,compact=false}:{guide?:StudyGuide|null;compact?:boolean}){
 if(!guide)return null;
 const example=<section className="kw-study-example"><h4>{guide.example.title}</h4><KnowledgeText text={guide.example.body}/></section>;
 const confusions=!!guide.common_confusions.length&&<section className="kw-study-confusions"><h4>容易混淆的地方</h4><dl>{guide.common_confusions.map((item,index)=><div key={index}><dt><KnowledgeText text={item.claim}/></dt><dd><KnowledgeText text={item.explanation}/></dd></div>)}</dl></section>;
 return <section className={'kw-node-study-guide'+(compact?' is-compact':'')} aria-label={compact?'节点基础讲解':'知识基础讲解'}>
  <header><h3>{compact?'直观理解':guide.title}</h3><span>{guide.kind==='reading_outline'?'阅读指引':'通用教学'}</span></header>
  <KnowledgeText text={guide.overview}/>
  <section className="kw-study-purpose"><h4>为什么会用到它</h4><KnowledgeText text={guide.why_it_matters}/></section>
  {compact?<>
   {!!guide.key_points.length&&<ul className="kw-study-key-points">{guide.key_points.slice(0,2).map((point,index)=><li key={index}><KnowledgeText text={point}/></li>)}</ul>}
   <details><summary>看一个例子</summary>{example}</details>
   {!!guide.common_confusions.length&&<details><summary>常见疑问</summary>{confusions}</details>}
  </>:<>
   {!!guide.flow.length&&<section><h4>一步步看它怎样工作</h4><ol className="kw-study-flow">{guide.flow.map((item,index)=><li key={index}><strong>{item.label}</strong><KnowledgeText text={item.text}/></li>)}</ol></section>}
   {example}
   {!!guide.key_points.length&&<section><h4>抓住这几个要点</h4><ul className="kw-study-key-points">{guide.key_points.map((point,index)=><li key={index}><KnowledgeText text={point}/></li>)}</ul></section>}
   {confusions}
   {guide.boundary&&<section><h4>适用条件</h4><KnowledgeText text={guide.boundary}/></section>}
   {!!guide.questions.length&&<details className="kw-study-questions"><summary>用自己的话想一想</summary><ol>{guide.questions.map((question,index)=><li key={index}><KnowledgeText text={question}/></li>)}</ol></details>}
   {!!guide.references?.length&&<details><summary>参考原文</summary><ul>{guide.references.filter(item=>/^https?:\/\//i.test(item.url)).map(item=><li key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></li>)}</ul></details>}
  </>}
 </section>;
}

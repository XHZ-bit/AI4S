import {useState} from 'react';
import {Button} from 'antd';
import type {FormulaSource,KnowledgeEvidence} from '../../api/knowledge';
import MathText,{renderMath} from '../learning/MathText';
import './source-formulas.css';

function SourceFormula({item,evidence,onEvidence}:{item:FormulaSource;evidence:KnowledgeEvidence[];onEvidence:(e:KnowledgeEvidence)=>void}){
 const [imageFailed,setImageFailed]=useState(false),[expanded,setExpanded]=useState(false);
 const source=evidence.find(e=>e.id===item.evidence_id);
 const latex=item.latex&&renderMath(item.latex,true)!==null?item.latex:undefined;
 const image=item.image_url&&!imageFailed&&/^\/api\//.test(item.image_url)?item.image_url:undefined;
 if(!latex&&!image&&!source)return null;
 const original=image?<div className={'kw-formula-image'+(expanded?' kw-formula-image-expanded':'')}><img src={image} alt={(item.page?'第 '+item.page+' 页':'原文')+'公式原图'} loading="lazy" onError={()=>setImageFailed(true)}/></div>:null;
 return <figure className="kw-source-formula" data-recognition={item.recognition}>
  {latex?<><MathText text={'$$'+latex+'$$'}/>{original&&<details><summary>核对公式原图</summary>{original}</details>}</>:original}
  <figcaption>{!latex&&<span>{image?'原文公式':'公式文本识别不完整'}{item.page?' · 第 '+item.page+' 页':''}</span>}{!latex&&image&&<Button size="small" type="link" aria-pressed={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?'适应宽度':'放大公式'}</Button>}{source&&<Button size="small" type="link" onClick={()=>onEvidence(source)}>查看公式原文</Button>}</figcaption>
 </figure>;
}
export default function SourceFormulas({items,evidence,onEvidence}:{items:FormulaSource[];evidence:KnowledgeEvidence[];onEvidence:(e:KnowledgeEvidence)=>void}){
 if(!items.length)return null;
 return <>{Array.from(new Map(items.map(item=>[item.block_id,item])).values()).map(item=><SourceFormula key={item.block_id} item={item} evidence={evidence} onEvidence={onEvidence}/>)}</>;
}

import {useState} from 'react';
import {Button} from 'antd';
import MathText from '../learning/MathText';
import './knowledge-experience.css';

export function safeRichUrl(value:string){
 if(/[\u0000-\u0020\u007f\\]/.test(value))return undefined;
 if(/^\/api\//.test(value))return value;
 try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:undefined}catch{return undefined}
}
function RichImage({label,url}:{label:string;url:string}){
 const [open,setOpen]=useState(false),[failed,setFailed]=useState(false);const href=safeRichUrl(url);
 if(!href)return <span>{label}（图片地址不可用）</span>;
 return <figure className="kw-rich-image"><figcaption>{label||'补充图片'} <a href={href} target="_blank" rel="noopener noreferrer">打开图片来源</a></figcaption>{!open?<button onClick={()=>setOpen(true)}>查看图片</button>:failed?<p>图片暂时无法加载，请打开来源查看。</p>:<img src={href} alt={label||'补充图片'} loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/>}</figure>;
}
function RichText({text}:{text:string}){
 // Math and inline code are kept intact; only explicit Markdown links/images become elements.
 const parts=text.split(/(\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)[^$\n]+?(?<!\\)\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|`[^`]+`|!?\[[^\]\n]*\]\([^\s)]+\))/g);
 return <>{parts.filter(Boolean).map((part,i)=>{const m=part.match(/^(!?)\[([^\]\n]*)\]\(([^\s)]+)\)$/);if(!m)return <MathText key={i} text={part}/>;if(m[1])return <RichImage key={i} label={m[2]} url={m[3]}/>;const url=safeRichUrl(m[3]);return url?<a key={i} href={url} target="_blank" rel="noopener noreferrer">{m[2]||url}</a>:<span key={i}>{m[2]}（链接地址不可用）</span>})}</>;
}

function CodeBlock({text}:{text:string}){
 const [copied,setCopied]=useState(false);const first=text.indexOf('\n');const language=first<0?'':text.slice(3,first).trim();const code=(first<0?text.slice(3):text.slice(first+1)).replace(/```\s*$/,'').trimEnd();
 return <div className="kw-learning-code"><div><span>{language||'代码示例'}</span><Button type="text" size="small" onClick={()=>{void navigator.clipboard?.writeText(code).then(()=>setCopied(true)).catch(()=>setCopied(false))}}>{copied?'已复制':'复制代码'}</Button></div><pre><code>{code}</code></pre></div>;
}
export function mathAwareText(text:string,latex?:unknown){return typeof latex==='string'&&text.trim()===latex.trim()?'$$'+latex+'$$':text;}
export default function KnowledgeText({text}:{text:string}){
 return <>{text.split(/(```[^\n]*\n[\s\S]*?```)/g).filter(Boolean).map((part,index)=>part.startsWith('```')?<CodeBlock key={index} text={part}/>:<RichText key={index} text={part}/>)}</>;
}

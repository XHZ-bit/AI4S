import {useState} from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import './math-text.css';

type MathPart = {kind:'text'|'math'|'code';raw:string;value:string;display?:boolean};
// Code and links stay intact. A matched LaTeX environment is an explicit formula
// even when the original node has no separate metadata.latex field.
const protectedParts = /```[^\n]*\n[\s\S]*?(?:```|$)|~~~[^\n]*\n[\s\S]*?(?:~~~|$)|`+[^`\n]*`+|!?\[[^\]\n]*\]\([^\s)]+\)|(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$(?!\$)[^$]*?(?<!\\)\$|(?<!\\)\\\[[\s\S]*?\\\]|(?<!\\)\\\([\s\S]*?\\\)|(?<!\\)\\begin\{(?<environment>[A-Za-z]+\*?)\}[\s\S]*?\\end\{\k<environment>\}/g;
const mathCommand = /\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|lim|log|exp|sin|cos|tanh|softmax|operatorname|mathrm|mathbf|mathcal|mathbb|boldsymbol|left|right|hat|vec|underbrace|overbrace|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|nu|pi|rho|sigma|tau|phi|omega|Delta|Theta|Sigma|Omega)\b/;

function delimited(text:string):{value:string;display:boolean}|undefined {
 const value=text.trim();
 if(value.startsWith('$$')&&value.endsWith('$$')&&value.length>=4)return {value:value.slice(2,-2),display:true};
 if(value.startsWith('\\[')&&value.endsWith('\\]'))return {value:value.slice(2,-2),display:true};
 if(value.startsWith('\\(')&&value.endsWith('\\)'))return {value:value.slice(2,-2),display:false};
 if(value.startsWith('$')&&value.endsWith('$')&&value.length>=2)return {value:value.slice(1,-1),display:false};
}

/** Wrap known formula fields once, without changing the saved expression. */
export function displayMath(text:string){return delimited(text)?text:'$$'+text+'$$';}
export function inlineMath(text:string){return delimited(text)?text:'$'+text+'$';}

function bareFormula(line:string){
 const value=line.trim();
 // Require explicit TeX, or a compact formula left hand side and math commands.
 return /^\\{1,2}(?:begin\{|[A-Za-z]+\s*\{)/.test(value)
  || mathCommand.test(value)&&(/^\\/.test(value)||/^[A-Za-z][A-Za-z\d_{}^]*(?:\([^()\n]*\))?\s*(?:=|\\(?:sim|approx|equiv|propto|in)\b)/.test(value));
}

function plainParts(text:string):MathPart[]{
 return text.split(/(\n\s*\n)/).filter(Boolean).flatMap<MathPart>(paragraph=>{
  if(damagedMathText(paragraph))return [{kind:'text' as const,raw:paragraph,value:paragraph}];
  const unfinished=/(?<!\\)\\{1,2}(?:begin\{|\[|\()/.exec(paragraph);
  if(unfinished)return [...(unfinished.index?[{kind:'text' as const,raw:paragraph.slice(0,unfinished.index),value:paragraph.slice(0,unfinished.index)}]:[]),
   {kind:'math' as const,raw:paragraph.slice(unfinished.index),value:paragraph.slice(unfinished.index),display:true}];
  return paragraph.split(/(\n)/).filter(Boolean).flatMap<MathPart>(line=>{
  if(bareFormula(line))return [{kind:'math' as const,raw:line,value:line.trim(),display:true}];
  const marker=/(?<!\\)\\(?:begin\{|\[|\()/.exec(line)
   || /(?<!\\)\$(?=[^$]*(?:\\[A-Za-z]|[_^{}=]))/.exec(line);
  if(marker)return [...(marker.index?[{kind:'text' as const,raw:line.slice(0,marker.index),value:line.slice(0,marker.index)}]:[]),
   {kind:'math' as const,raw:line.slice(marker.index),value:line.slice(marker.index),display:false}];
  return [{kind:'text' as const,raw:line,value:line}];
  });
 });
}

export function mathTextParts(text:string):MathPart[]{
 const parts:MathPart[]=[];let cursor=0;
 for(const match of text.matchAll(protectedParts)){
  const index=match.index!,raw=match[0];
  if(index>cursor)parts.push(...plainParts(text.slice(cursor,index)));
  if(raw.startsWith('```')||raw.startsWith('~~~'))parts.push({kind:'code',raw,value:raw,display:true});
  else if(raw.startsWith('`'))parts.push({kind:'code',raw,value:raw.replace(/^`+|`+$/g,''),display:false});
  else if(/^!?\[/.test(raw))parts.push({kind:'text',raw,value:raw});
  else {const math=delimited(raw);parts.push({kind:'math',raw,value:math?.value??raw,display:math?.display??true});}
  cursor=index+raw.length;
 }
 if(cursor<text.length)parts.push(...plainParts(text.slice(cursor)));
 return parts;
}

export function damagedMathText(text:string){
 if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text))return true;
 return text.includes('\uFFFD')&&(/[=∑πµΔδθ]|\\(?:frac|sum|begin)|\b(?:tanh|arccos|exp)\b/.test(text)||text.split('\n').filter(line=>line.trim().length<18).length>5);
}

export function renderMath(text:string,displayMode=false){
 const original=delimited(text)?.value??text;
 // CRLF is a source line ending; lone CR / tabs can be decoded \rho / \theta.
 const value=original.replace(/\r\n/g,'\n');
 if(value.length>30000||damagedMathText(value)||/[\t\r]/.test(value)||!displayMode&&value.includes('\n'))return null;
 if(/(?<!\\)\\\\(?:begin|frac|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|nu|pi|rho|sigma|tau|phi|omega)\b/.test(value))return null;
 try{return katex.renderToString(value,{displayMode,throwOnError:true,trust:false,strict:'ignore',maxExpand:1000})}catch{return null}
}

function MathFallback({text,damaged,showSource}:{text:string;damaged:boolean;showSource:boolean}){
 const [open,setOpen]=useState(false);
 const source=text.replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g,char=>'\\u'+char.charCodeAt(0).toString(16).padStart(4,'0'));
 return <span className="learning-math-fallback"><span className="learning-math-source-needed" role="note">{damaged?'公式文本识别不完整，请查看原文公式。':'公式排版未完成，请查看原文公式。'}</span>{showSource&&<><button type="button" className="learning-math-source-toggle" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'收起原式':'查看原式'}</button>{open&&<code className="learning-math-original">{source}</code>}</>}</span>;
}

export default function MathText({text,showSourceOnError=false}:{text:string;showSourceOnError?:boolean}){
 const parts=mathTextParts(text);
 return <>{parts.map((part,i)=>{
  if(part.kind==='code')return part.display?<pre key={i}><code>{part.raw}</code></pre>:<code key={i}>{part.value}</code>;
  if(damagedMathText(part.raw))return <MathFallback key={i} text={part.raw} damaged showSource={showSourceOnError}/>;
  if(part.kind==='math'){
   const html=renderMath(part.value,part.display);
   return html===null?<MathFallback key={i} text={part.raw} damaged={/[\t\r]/.test(part.value)} showSource={showSourceOnError}/>
    :<span key={i} className={part.display?'learning-math-display':'learning-math'} dangerouslySetInnerHTML={{__html:html}}/>;
  }
  return <span key={i} style={{whiteSpace:'pre-wrap'}}>{part.value.split(/(\*\*[^*]+\*\*)/g).map((piece,j)=>piece.startsWith('**')?<strong key={j}>{piece.slice(2,-2)}</strong>:piece)}</span>;
 })}</>;
}

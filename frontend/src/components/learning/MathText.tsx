import katex from "katex";
import "katex/dist/katex.min.css";
export function renderMath(text:string,displayMode=false){
 if(damagedMathText(text))return null;
 try{return katex.renderToString(text,{displayMode,throwOnError:true,trust:false,strict:'ignore'})}catch{return null}
}
export function damagedMathText(text:string){
 if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text))return true;
 return text.includes('\uFFFD')&&(/[=∑πµΔδθ]|\\(?:frac|sum|begin)|\b(?:tanh|arccos|exp)\b/.test(text)||text.split('\n').filter(line=>line.trim().length<18).length>5);
}
export default function MathText({text}:{text:string}){
 const pieces=text.split(/(\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)[^$\n]+?(?<!\\)\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))/g).flatMap(part=>part.startsWith('$')||part.startsWith('\\[')||part.startsWith('\\(')?[part]:part.split(/(\n\s*\n)/g));
 return <>{pieces.map((part,i)=>{
  if(damagedMathText(part))return <span key={i} className="learning-math-source-needed" role="note">公式文本识别不完整，请查看原文公式。</span>;
  const dollar=part.startsWith('$'),bracket=part.startsWith('\\['),paren=part.startsWith('\\('),display=part.startsWith('$$')||bracket;
  if(dollar||bracket||paren){const count=dollar&&!display?1:2,html=renderMath(part.slice(count,-count),display);return html===null?<span key={i} className="learning-math-source-needed" role="note">公式排版未完成，请查看原文公式。</span>:<span key={i} className={display?'learning-math-display':'learning-math'} dangerouslySetInnerHTML={{__html:html}}/>}
  return <span key={i} style={{whiteSpace:'pre-wrap'}}>{part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((piece,j)=>piece.startsWith('**')?<strong key={j}>{piece.slice(2,-2)}</strong>:piece.startsWith('`')?<code key={j}>{piece.slice(1,-1)}</code>:piece)}</span>;
 })}</>;
}

import './knowledge-experience.css';

export const VISUAL_PREFIX='PAPERSTRIDE_VISUAL:';
type Point=[number,number];
export interface PracticeVisual {type:'line'|'bar'|'scatter'|'table';title:string;x_label:string;y_label:string;series:{name:string;points:Point[]}[];columns:string[];rows:(string|number|null)[][]}
const text=(v:unknown,max=180)=>typeof v==='string'?v.slice(0,max):'';
export function validatePracticeVisual(value:unknown):PracticeVisual|null{
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const v=value as Record<string,unknown>;
 if(!['line','bar','scatter','table'].includes(String(v.type)))return null;
 const base={type:v.type as PracticeVisual['type'],title:text(v.title)||'教学运行可视化',x_label:text(v.x_label,60)||'x',y_label:text(v.y_label,60)||'y',series:[],columns:[],rows:[]} as PracticeVisual;
 if(v.type==='table'){
  if(!Array.isArray(v.columns)||!v.columns.length||v.columns.length>12||!v.columns.every(x=>typeof x==='string')||!Array.isArray(v.rows)||v.rows.length>200)return null;
  const width=v.columns.length;
  if(!v.rows.every(r=>Array.isArray(r)&&r.length===width&&r.every(x=>x===null||typeof x==='string'&&x.length<=1000||typeof x==='number'&&Number.isFinite(x))))return null;
  return {...base,columns:v.columns.map(x=>text(x,100)),rows:v.rows as PracticeVisual['rows']};
 }
 if(!Array.isArray(v.series)||!v.series.length||v.series.length>6)return null;
 const series:PracticeVisual['series']=[];
 for(const raw of v.series){
  if(!raw||typeof raw!=='object'||!Array.isArray(raw.points)||!raw.points.length||raw.points.length>500)return null;
  if(!raw.points.every((p:unknown)=>Array.isArray(p)&&p.length===2&&p.every(x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=1e12)))return null;
  series.push({name:text(raw.name,100)||`数据 ${series.length+1}`,points:raw.points as Point[]});
 }
 return {...base,series};
}
export function parsePracticeOutput(output:string){
 const visuals:PracticeVisual[]=[],lines:string[]=[],warnings:string[]=[];
 for(const line of output.split('\n')){
  if(!line.startsWith(VISUAL_PREFIX)){lines.push(line);continue}
  if(visuals.length>=4){warnings.push('一次运行最多展示 4 幅图表，其余内容保留在原始输出。');lines.push(line);continue}
  let value:PracticeVisual|null=null;try{if(line.length<=150000)value=validatePracticeVisual(JSON.parse(line.slice(VISUAL_PREFIX.length)))}catch{/* Show invalid data as text instead of executing it. */}
  if(value)visuals.push(value);else{warnings.push('有一项图表数据格式无效，已保留原始输出。');lines.push(line)}
 }
 return {visuals,text:lines.join('\n').trim(),warnings:[...new Set(warnings)]};
}
const colors=['#365e4e','#3765a0','#a65d27','#825896','#547b79','#9c4d5b'];
function ValuesTable({columns,rows}:{columns:string[];rows:PracticeVisual['rows']}){return <div className="kw-visual-table"><table><thead><tr>{columns.map((column,i)=><th key={i} scope="col">{column}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{v===null?'—':String(v)}</td>)}</tr>)}</tbody></table></div>}
function Chart({data}:{data:PracticeVisual}){
 const points=data.series.flatMap(s=>s.points),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
 let minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
 if(data.type==='bar'){minY=Math.min(0,minY);maxY=Math.max(0,maxY)}
 if(minX===maxX){minX-=1;maxX+=1}if(minY===maxY){minY-=1;maxY+=1}
 const x=(v:number)=>65+(v-minX)/(maxX-minX)*450,y=(v:number)=>255-(v-minY)/(maxY-minY)*215;
 const tick=(v:number)=>Number(v.toPrecision(4)).toString(),zeroY=y(Math.min(maxY,Math.max(minY,0)));
 return <><svg viewBox="0 0 580 315" role="img" aria-label={data.title} className="kw-practice-chart"><title>{data.title}</title>{Array.from({length:5},(_,i)=>{const val=minY+(maxY-minY)*i/4,yy=y(val);return <g key={i}><line x1="65" x2="515" y1={yy} y2={yy} className="kw-chart-grid"/><text x="56" y={yy+4} textAnchor="end">{tick(val)}</text></g>})}<path d="M65 40V255H515" className="kw-chart-axis"/>{Array.from({length:5},(_,i)=>{const val=minX+(maxX-minX)*i/4;return <text key={i} x={x(val)} y="276" textAnchor="middle">{tick(val)}</text>})}<text x="290" y="307" textAnchor="middle">{data.x_label}</text><text x="17" y="147" transform="rotate(-90 17 147)" textAnchor="middle">{data.y_label}</text>{data.series.map((s,i)=><g key={i} style={{color:colors[i]}}>{data.type==='line'?<polyline points={s.points.map(p=>`${x(p[0])},${y(p[1])}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray={i%2?'6 3':undefined}/>:s.points.map((p,j)=>data.type==='scatter'?<circle key={j} cx={x(p[0])} cy={y(p[1])} r="4" fill="currentColor"><title>{s.name}: {p[0]}, {p[1]}</title></circle>:<rect key={j} x={x(p[0])-Math.min(10,180/s.points.length)/2} y={Math.min(zeroY,y(p[1]))} width={Math.min(10,180/s.points.length)} height={Math.max(1,Math.abs(y(p[1])-zeroY))} fill="currentColor" opacity={.9-i*.1}><title>{s.name}: {p[0]}, {p[1]}</title></rect>)}</g>)}</svg><ul className="kw-chart-legend">{data.series.map((s,i)=><li key={i}><span style={{background:colors[i]}}/>{s.name}</li>)}</ul><details><summary>查看绘图数据</summary><ValuesTable columns={['数据系列',data.x_label,data.y_label]} rows={data.series.flatMap(s=>s.points.map(p=>[s.name,...p]))}/></details></>;
}
export default function PracticeVisuals({output}:{output:string}){
 const parsed=parsePracticeOutput(output);
 return <>{parsed.text&&<pre>{parsed.text}</pre>}{parsed.warnings.map(w=><p role="note" key={w}>{w}</p>)}{parsed.visuals.map((data,i)=><figure className="kw-practice-visual" key={i}><figcaption>{data.title}</figcaption>{data.type==='table'?<ValuesTable columns={data.columns} rows={data.rows}/>:<Chart data={data}/>}</figure>)}</>;
}
export const VISUAL_EXAMPLE=`
# PaperStride 通用绘图示例：y = scale * x。用于学习绘图，不代表论文结果。
import json
visual_scale = float(inputs.get("visual_scale", 1)) if isinstance(inputs, dict) else 1.0
visual_points = [[x / 10, visual_scale * x / 10] for x in range(-20, 21)]
print("PAPERSTRIDE_VISUAL:" + json.dumps({"type": "line", "title": "改变 visual_scale，观察线性缩放", "x_label": "x", "y_label": "scale × x", "series": [{"name": "线性缩放", "points": visual_points}]}, ensure_ascii=False))
`;

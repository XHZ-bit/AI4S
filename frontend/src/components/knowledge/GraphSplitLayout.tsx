import {useLayoutEffect,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {useCurrentAccount} from '../SessionContext';
import './graph-split-layout.css';

export interface GraphDetailControls {
 expanded:boolean;
 canSplit:boolean;
 onToggleExpanded:()=>void;
 onResetWidth:()=>void;
}
export const graphDetailWidthKey=(account:string|undefined,project:string)=>`paperstride:${account||'local'}:graph-detail-width:${project}`;
const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
function readWidth(key:string):number|undefined {
 try{const value=JSON.parse(localStorage.getItem(key)||'null');return typeof value==='number'&&Number.isFinite(value)&&value>=320&&value<=880?value:undefined}catch{return undefined}
}

/** Keep the canvas mounted while expanding details so drafts and the graph camera survive. */
export default function GraphSplitLayout(props:{projectId:string;children:ReactNode;detail?:(controls:GraphDetailControls)=>ReactNode;onCanvasHeight:(height:number)=>void}) {
 const account=useCurrentAccount(),storageKey=graphDetailWidthKey(account?.id,props.projectId);
 return <ScopedGraphSplitLayout key={storageKey} {...props} storageKey={storageKey}/>;
}
function ScopedGraphSplitLayout({children,detail,onCanvasHeight,storageKey}:{children:ReactNode;detail?:(controls:GraphDetailControls)=>ReactNode;onCanvasHeight:(height:number)=>void;storageKey:string}) {
 const root=useRef<HTMLDivElement>(null);
 const [bounds,setBounds]=useState({width:1000,available:480}),[preferred,setPreferred]=useState(()=>readWidth(storageKey));
 const [expanded,setExpanded]=useState(false),[resizing,setResizing]=useState(false),[saveError,setSaveError]=useState(false);
 const dragging=useRef<{pointerId:number;x:number;width:number;value:number}>();
 const max=Math.max(320,Math.min(880,bounds.width-320-12)),min=320;
 const width=clamp(preferred??clamp(Math.round(bounds.width*.4),420,560),min,max);
 const canSplit=bounds.width>=652,single=!!detail&&(expanded||!canSplit);
 const graphWidth=detail&&!single?bounds.width-width-12:bounds.width;
 const controlsHeight=graphWidth<460?116:graphWidth<760?84:48;
 const canvasHeight=Math.max(260,bounds.available-controlsHeight),areaHeight=canvasHeight+controlsHeight;
 useLayoutEffect(()=>{
  const element=root.current;if(!element)return;
  const measure=()=>{
   const rect=element.getBoundingClientRect();
   const next={width:Math.round(rect.width||element.clientWidth||1000),available:Math.floor(window.innerHeight-Math.max(0,rect.top)-20)};
   setBounds(old=>old.width===next.width&&old.available===next.available?old:next);
  };
  measure();const observer=new ResizeObserver(measure);observer.observe(element);
  const graph=element.closest('.kw-graph-view'),workspace=element.closest('.kw-workspace');
  if(graph)observer.observe(graph);if(workspace)observer.observe(workspace);
  window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure)};
 },[expanded]);
 useLayoutEffect(()=>{onCanvasHeight(canvasHeight)},[canvasHeight,onCanvasHeight]);
 const persist=(value:number|undefined)=>{
  try{if(value===undefined)localStorage.removeItem(storageKey);else localStorage.setItem(storageKey,JSON.stringify(value));setSaveError(false)}catch{setSaveError(true)}
 };
 const reset=()=>{setPreferred(undefined);persist(undefined)};
 const resize=(value:number,save=true)=>{const next=clamp(Math.round(value),min,max);setPreferred(next);if(save)persist(next);return next};
 const finish=()=>{if(dragging.current){persist(dragging.current.value);dragging.current=undefined;setResizing(false)}};
 return <div ref={root} className={'kw-graph-layout kw-resizable-graph'+(detail?' kw-has-inspector':'')+(single?' kw-detail-expanded':'')+(resizing?' kw-resizing-details':'')}
  style={{'--kw-detail-width':width+'px','--kw-canvas-height':canvasHeight+'px','--kw-work-area-height':areaHeight+'px'} as CSSProperties}>
  {children}
  {detail&&<>
   <div className="kw-detail-resizer" role="separator" tabIndex={0} aria-label="调整节点详情宽度" aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={width} aria-valuetext={width+'像素'}
    title="拖动调整宽度；方向键微调，双击恢复默认"
    onDoubleClick={reset}
    onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture?.(event.pointerId);dragging.current={pointerId:event.pointerId,x:event.clientX,width,value:width};setResizing(true)}}
    onPointerMove={event=>{const drag=dragging.current;if(!drag||drag.pointerId!==event.pointerId)return;drag.value=resize(drag.width+drag.x-event.clientX,false)}}
    onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}
    onKeyDown={event=>{const step=event.shiftKey?64:16;let next:number;if(event.key==='ArrowLeft')next=width+step;else if(event.key==='ArrowRight')next=width-step;else if(event.key==='Home')next=min;else if(event.key==='End')next=max;else if(event.key==='Enter'){event.preventDefault();reset();return}else return;event.preventDefault();resize(next)}}
   ><span aria-hidden="true"/></div>
   {detail({expanded:single,canSplit,onToggleExpanded:()=>{if(canSplit)setExpanded(value=>!value)},onResetWidth:reset})}
  </>}
  {saveError&&<p className="kw-detail-save-error" role="status">宽度已调整，浏览器暂时无法记住此设置。</p>}
 </div>;
}

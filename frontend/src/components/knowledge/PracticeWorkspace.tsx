import {useLayoutEffect,useRef,useState,type CSSProperties,type KeyboardEvent,type ReactNode} from 'react';
import {useCurrentAccount} from '../SessionContext';
import './practice-workspace.css';

export type PracticeTaskTab='instructions'|'input'|'history'|'settings';
export type PracticeResultTab='output'|'analysis';
export interface PracticeTaskFocus {tab:PracticeTaskTab;nonce:string|number}
export interface PracticeResultFocus {tab:PracticeResultTab;nonce:string|number}
export interface PracticeWorkspaceProps {
 projectId:string;
 nodeId:string;
 instructions:ReactNode;
 input:ReactNode;
 history:ReactNode;
 settings?:ReactNode;
 editor:ReactNode;
 editorToolbar?:ReactNode;
 actions:ReactNode;
 output:ReactNode;
 analysis:ReactNode;
 taskFocus?:PracticeTaskFocus;
 resultFocus?:PracticeResultFocus;
}
interface Layout {sidebarWidth?:number;resultHeight?:number}
interface Bounds {width:number;height:number;chrome:number}
const DIVIDER=12,MIN_TASK=260,MAX_TASK=380,MIN_CODE_WIDTH=480,MIN_EDITOR=180,MIN_RESULT=100;
const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
const taskLabels:[PracticeTaskTab,string][]=[['instructions','题目'],['input','输入'],['history','学习记录'],['settings','设置']];
const resultLabels:[PracticeResultTab,string][]=[['output','运行结果'],['analysis','AI 分析']];
export const practiceWorkspaceKey=(account:string|undefined,project:string,node:string)=>
 'paperstride:practice-layout:'+JSON.stringify([account||'local',project,node]);
function readLayout(key:string):Layout {
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null');
  return {
   sidebarWidth:typeof value?.sidebarWidth==='number'&&Number.isFinite(value.sidebarWidth)&&value.sidebarWidth>=MIN_TASK&&value.sidebarWidth<=MAX_TASK?value.sidebarWidth:undefined,
   resultHeight:typeof value?.resultHeight==='number'&&Number.isFinite(value.resultHeight)&&value.resultHeight>=MIN_RESULT&&value.resultHeight<=3000?value.resultHeight:undefined,
  };
 }catch{return {}}
}
function chooseWithKeyboard<T>(event:KeyboardEvent,index:number,items:[T,string][],choose:(value:T,index:number)=>void){
 let next=index;
 if(event.key==='ArrowRight')next=(index+1)%items.length;
 else if(event.key==='ArrowLeft')next=(index+items.length-1)%items.length;
 else if(event.key==='Home')next=0;
 else if(event.key==='End')next=items.length-1;
 else return;
 event.preventDefault();choose(items[next][0],next);
}

/** Layout only: slots stay mounted while tabs, dimensions and run results change. */
export default function PracticeWorkspace(props:PracticeWorkspaceProps){
 const account=useCurrentAccount(),storageKey=practiceWorkspaceKey(account?.id,props.projectId,props.nodeId);
 return <ScopedPracticeWorkspace key={storageKey} {...props} storageKey={storageKey}/>;
}
function ScopedPracticeWorkspace({instructions,input,history,settings,editor,editorToolbar,actions,output,analysis,taskFocus,resultFocus,storageKey}:PracticeWorkspaceProps&{storageKey:string}){
 const root=useRef<HTMLDivElement>(null),toolbar=useRef<HTMLDivElement>(null),actionBar=useRef<HTMLDivElement>(null);
 const [bounds,setBounds]=useState<Bounds>({width:1080,height:500,chrome:48+(editorToolbar?36:0)});
 const [layout,setLayout]=useState<Layout>(()=>readLayout(storageKey)),layoutRef=useRef(layout);
 const [taskTab,setTaskTab]=useState<PracticeTaskTab>('instructions'),[resultTab,setResultTab]=useState<PracticeResultTab>('output');
 const [resizing,setResizing]=useState<'task'|'result'>(),[saveError,setSaveError]=useState(false);
 const dragging=useRef<{axis:'task'|'result';pointerId:number;start:number;value:number;initial:number}>();
 const taskButtons=useRef<(HTMLButtonElement|null)[]>([]),resultButtons=useRef<(HTMLButtonElement|null)[]>([]);
 const taskTabs=taskLabels.filter(([id])=>id!=='settings'||settings!==undefined);
 const maxTask=Math.max(MIN_TASK,Math.min(MAX_TASK,bounds.width-MIN_CODE_WIDTH-DIVIDER));
 const taskWidth=clamp(layout.sidebarWidth??Math.round(bounds.width*.3),MIN_TASK,maxTask);
 const maxResult=Math.max(MIN_RESULT,bounds.height-bounds.chrome-MIN_EDITOR-DIVIDER);
 const resultHeight=clamp(layout.resultHeight??Math.round(Math.min(180,bounds.height*.33)),MIN_RESULT,maxResult);
 useLayoutEffect(()=>{
  const element=root.current;if(!element)return;
  const measure=()=>{
   const rect=element.getBoundingClientRect();
   const chrome=2+Math.round((toolbar.current?.getBoundingClientRect().height||0)+(actionBar.current?.getBoundingClientRect().height||48));
   const next={width:Math.round(rect.width||element.clientWidth||1080),height:Math.max(360,MIN_EDITOR+chrome+DIVIDER+MIN_RESULT,Math.floor(window.innerHeight-Math.max(0,rect.top)-20)),chrome};
   setBounds(old=>old.width===next.width&&old.height===next.height&&old.chrome===next.chrome?old:next);
  };
  measure();const observer=new ResizeObserver(measure);
  observer.observe(element);if(toolbar.current)observer.observe(toolbar.current);if(actionBar.current)observer.observe(actionBar.current);
  const workspace=element.closest('.kw-workspace');if(workspace)observer.observe(workspace);
  window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure)};
 },[editorToolbar!==undefined]);
 useLayoutEffect(()=>{if(taskFocus&&(taskFocus.tab!=='settings'||settings!==undefined))setTaskTab(taskFocus.tab)},[taskFocus?.tab,taskFocus?.nonce]);
 useLayoutEffect(()=>{if(resultFocus)setResultTab(resultFocus.tab)},[resultFocus?.tab,resultFocus?.nonce]);
 const persist=(next:Layout)=>{try{if(next.sidebarWidth===undefined&&next.resultHeight===undefined)localStorage.removeItem(storageKey);else localStorage.setItem(storageKey,JSON.stringify(next));setSaveError(false)}catch{setSaveError(true)}};
 const resize=(axis:'task'|'result',value:number,save=true)=>{
  const nextValue=Math.round(axis==='task'?clamp(value,MIN_TASK,maxTask):clamp(value,MIN_RESULT,maxResult));
  const next={...layoutRef.current,[axis==='task'?'sidebarWidth':'resultHeight']:nextValue};
  layoutRef.current=next;setLayout(next);if(save)persist(next);return nextValue;
 };
 const reset=(axis:'task'|'result')=>{const next={...layoutRef.current,[axis==='task'?'sidebarWidth':'resultHeight']:undefined};layoutRef.current=next;setLayout(next);persist(next)};
 const finish=()=>{if(dragging.current){persist(layoutRef.current);dragging.current=undefined;setResizing(undefined)}};
 const separator=(axis:'task'|'result')=>{
  const task=axis==='task',value=task?taskWidth:resultHeight,min=task?MIN_TASK:MIN_RESULT,max=task?maxTask:maxResult;
  return <div className={'kw-practice-ide-resizer kw-practice-ide-resizer-'+axis} role="separator" tabIndex={0} aria-label={task?'调整任务栏宽度':'调整结果区高度'} aria-orientation={task?'vertical':'horizontal'} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-valuetext={value+'像素'}
   title={'拖动调整'+(task?'任务栏宽度':'结果区高度')+'；方向键微调，双击恢复默认'}
   onDoubleClick={()=>reset(axis)}
   onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture?.(event.pointerId);dragging.current={axis,pointerId:event.pointerId,start:task?event.clientX:event.clientY,value,initial:value};setResizing(axis)}}
   onPointerMove={event=>{const drag=dragging.current;if(!drag||drag.axis!==axis||drag.pointerId!==event.pointerId)return;drag.value=resize(axis,drag.initial+(task?event.clientX-drag.start:drag.start-event.clientY),false)}}
   onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}
   onKeyDown={event=>{const step=event.shiftKey?48:16;let next:number;if(event.key===(task?'ArrowRight':'ArrowUp'))next=value+step;else if(event.key===(task?'ArrowLeft':'ArrowDown'))next=value-step;else if(event.key==='Home')next=min;else if(event.key==='End')next=max;else if(event.key==='Enter'){event.preventDefault();reset(axis);return}else return;event.preventDefault();resize(axis,next)}}
  ><span aria-hidden="true"/></div>;
 };
 const taskContent={instructions,input,history,settings};
 return <div ref={root} className={'kw-practice-ide'+(resizing?' kw-practice-ide-resizing-'+resizing:'')} style={{height:bounds.height,'--kw-practice-task-width':taskWidth+'px','--kw-practice-result-height':resultHeight+'px'} as CSSProperties}>
  <aside className="kw-practice-ide-task" aria-label="练习任务栏">
   <div role="tablist" aria-label="练习任务分区" className="kw-practice-ide-tabs">{taskTabs.map(([id,label],index)=><button key={id} type="button" role="tab" id={'kw-practice-task-'+id+'-tab'} aria-controls={'kw-practice-task-'+id+'-panel'} aria-selected={taskTab===id} tabIndex={taskTab===id?0:-1} ref={element=>{taskButtons.current[index]=element}} onClick={()=>setTaskTab(id)} onKeyDown={event=>chooseWithKeyboard(event,index,taskTabs,(next,position)=>{setTaskTab(next);taskButtons.current[position]?.focus()})}>{label}</button>)}</div>
   {taskTabs.map(([id])=><section key={id} role="tabpanel" id={'kw-practice-task-'+id+'-panel'} aria-labelledby={'kw-practice-task-'+id+'-tab'} hidden={taskTab!==id} tabIndex={0} className="kw-practice-ide-task-content">{taskContent[id]}</section>)}
   {saveError&&<p className="kw-practice-ide-save-error" role="status">布局已调整，浏览器暂时无法记住此设置。</p>}
  </aside>
  {separator('task')}
  <section className="kw-practice-ide-main" aria-label="代码与结果">
   <div className="kw-practice-ide-code">
    {editorToolbar!==undefined&&<div ref={toolbar} className="kw-practice-ide-editor-toolbar">{editorToolbar}</div>}
    <div className="kw-practice-ide-editor">{editor}</div>
    <div ref={actionBar} className="kw-practice-ide-actions" aria-label="代码运行操作">{actions}</div>
   </div>
   {separator('result')}
   <div className="kw-practice-ide-results" aria-label="运行结果与分析">
    <div role="tablist" aria-label="练习结果分区" className="kw-practice-ide-tabs">{resultLabels.map(([id,label],index)=><button key={id} type="button" role="tab" id={'kw-practice-result-'+id+'-tab'} aria-controls={'kw-practice-result-'+id+'-panel'} aria-selected={resultTab===id} tabIndex={resultTab===id?0:-1} ref={element=>{resultButtons.current[index]=element}} onClick={()=>setResultTab(id)} onKeyDown={event=>chooseWithKeyboard(event,index,resultLabels,(next,position)=>{setResultTab(next);resultButtons.current[position]?.focus()})}>{label}</button>)}</div>
    <section role="tabpanel" id="kw-practice-result-output-panel" aria-labelledby="kw-practice-result-output-tab" hidden={resultTab!=='output'} tabIndex={0} className="kw-practice-ide-result-content">{output}</section>
    <section role="tabpanel" id="kw-practice-result-analysis-panel" aria-labelledby="kw-practice-result-analysis-tab" hidden={resultTab!=='analysis'} tabIndex={0} className="kw-practice-ide-result-content">{analysis}</section>
   </div>
  </section>
 </div>;
}

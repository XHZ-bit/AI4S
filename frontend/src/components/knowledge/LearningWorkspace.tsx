import {useEffect,useLayoutEffect,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import LearningProgress from './LearningProgress';
import {useCurrentAccount} from '../SessionContext';
import './learning-workspace.css';

export type LearningReadTab='lesson'|'evidence'|'practice';
export type LearningToolTab='question'|'notes'|'records';
const readTabs:[LearningReadTab,string][]=[['lesson','讲解'],['evidence','原文依据'],['practice','练习与实现']];
const toolTabs:[LearningToolTab,string][]=[['question','提问'],['notes','笔记'],['records','学习记录']];
interface Scene {tab:LearningReadTab;scroll:Partial<Record<LearningReadTab,number>>}
interface ToolLayout {toolWidth?:number;collapsed?:boolean}
export const learningWorkspaceLayoutKey=(account:string|undefined,project:string)=>'paperstride:learning-layout:'+JSON.stringify([account||'local',project]);
function readToolLayout(key:string):ToolLayout {
 try{const value=JSON.parse(localStorage.getItem(key)||'null');return{toolWidth:typeof value?.toolWidth==='number'&&Number.isFinite(value.toolWidth)&&value.toolWidth>=280&&value.toolWidth<=480?value.toolWidth:undefined,collapsed:value?.collapsed===true}}catch{return{}}
}
function readFocused(key:string){try{return sessionStorage.getItem(key+':focused')==='true'}catch{return false}}
function readScene(key:string):Scene {
 try{const value=JSON.parse(sessionStorage.getItem(key)||'null');const scroll:Scene['scroll']={};for(const [tab] of readTabs){const top=value?.scroll?.[tab];if(typeof top==='number'&&Number.isFinite(top)&&top>=0)scroll[tab]=Math.min(top,1000000)}return {tab:readTabs.some(([tab])=>tab===value?.tab)?value.tab:'lesson',scroll}}catch{return {tab:'lesson',scroll:{}}}
}

export default function LearningWorkspace(props:{projectId:string;nodeId:string;focusResources?:boolean;tool:LearningToolTab;onTool:(tool:LearningToolTab)=>void;onNode:(id:string)=>void;lesson:ReactNode;evidence:ReactNode;practice:ReactNode;question:ReactNode;notes:ReactNode;chapters:{id:string;label:string}[]}) {
 const account=useCurrentAccount(),scope=JSON.stringify([account?.id||'local',props.projectId,props.nodeId]);
 return <ScopedLearningWorkspace key={scope} {...props} storageKey={'paperstride:learning-reader:'+scope} layoutKey={learningWorkspaceLayoutKey(account?.id,props.projectId)}/>;
}
function ScopedLearningWorkspace({projectId,nodeId,focusResources,tool,onTool,onNode,lesson,evidence,practice,question,notes,chapters,storageKey,layoutKey}:{projectId:string;nodeId:string;focusResources?:boolean;tool:LearningToolTab;onTool:(tool:LearningToolTab)=>void;onNode:(id:string)=>void;lesson:ReactNode;evidence:ReactNode;practice:ReactNode;question:ReactNode;notes:ReactNode;chapters:{id:string;label:string}[];storageKey:string;layoutKey:string}) {
 const initial=useRef(focusResources?{...readScene(storageKey),tab:'practice' as const}:readScene(storageKey)),[tab,setTab]=useState<LearningReadTab>(initial.current.tab),[visited,setVisited]=useState(()=>new Set<LearningReadTab>(['lesson',initial.current.tab])),[bounds,setBounds]=useState({height:480,width:1000});
 const scene=useRef(initial.current),root=useRef<HTMLDivElement>(null),panels=useRef<Partial<Record<LearningReadTab,HTMLElement>>>({}),mainButtons=useRef<(HTMLButtonElement|null)[]>([]),toolButtons=useRef<(HTMLButtonElement|null)[]>([]);
 const [layout,setLayout]=useState(()=>readToolLayout(layoutKey)),layoutRef=useRef(layout),[focused,setFocused]=useState(()=>readFocused(layoutKey)),[narrowToolOpen,setNarrowToolOpen]=useState(false),[resizing,setResizing]=useState(false);
 const measureRef=useRef<()=>void>(),focusButton=useRef<HTMLButtonElement>(null),toolsButton=useRef<HTMLButtonElement>(null),focusTool=useRef<LearningToolTab>(),focusReader=useRef(false),dragging=useRef<{pointerId:number;x:number;width:number}>();
 const canSplit=bounds.width>=892,collapsed=!!layout.collapsed||(!canSplit&&!narrowToolOpen),fullWidthTools=!canSplit&&!collapsed,maxWidth=Math.max(280,Math.min(480,bounds.width-600-12));
 const toolWidth=Math.max(280,Math.min(maxWidth,layout.toolWidth??320));
 const persist=()=>{try{sessionStorage.setItem(storageKey,JSON.stringify(scene.current))}catch{/* Reading remains available when session storage is blocked. */}};
 const saveLayout=(value:ToolLayout)=>{layoutRef.current=value;setLayout(value);try{localStorage.setItem(layoutKey,JSON.stringify(value))}catch{/* The current layout remains usable without browser storage. */}};
 const openTool=(next:LearningToolTab)=>{focusTool.current=next;saveLayout({...layoutRef.current,collapsed:false});setNarrowToolOpen(true);onTool(next)};
 const closeTools=()=>{focusReader.current=true;saveLayout({...layoutRef.current,collapsed:true});setNarrowToolOpen(false)};
 const changeFocus=(next:boolean)=>{setFocused(next);try{sessionStorage.setItem(layoutKey+':focused',String(next))}catch{/* Focus mode remains available for this visit. */}};
 const resize=(width:number,save=true)=>{const next={...layoutRef.current,toolWidth:Math.max(280,Math.min(maxWidth,Math.round(width)))};layoutRef.current=next;setLayout(next);if(save)saveLayout(next)};
 const resetWidth=()=>saveLayout({...layoutRef.current,toolWidth:undefined});
 const finishResize=()=>{if(dragging.current){dragging.current=undefined;setResizing(false);saveLayout(layoutRef.current)}};
 const select=(next:LearningReadTab)=>{scene.current.tab=next;setTab(next);setVisited(old=>new Set([...old,next]));persist()};
 useLayoutEffect(()=>{
  const element=root.current;if(!element)return;
  const measure=()=>{const rect=element.getBoundingClientRect(),next={height:Math.max(280,Math.floor(window.innerHeight-Math.max(0,rect.top)-12)),width:Math.round(rect.width||element.clientWidth||1000)};setBounds(old=>old.height===next.height&&old.width===next.width?old:next)};
  measureRef.current=measure;measure();const observer=new ResizeObserver(measure);observer.observe(element);const space=element.closest('.kw-workspace');if(space)observer.observe(space);const header=element.closest('.kw-learning-studio')?.querySelector('.kw-learning-studio-header');if(header)observer.observe(header);window.addEventListener('resize',measure);
  return()=>{measureRef.current=undefined;observer.disconnect();window.removeEventListener('resize',measure);persist()};
 },[]);
 useLayoutEffect(()=>{measureRef.current?.()},[focused,collapsed,fullWidthTools]);
 useLayoutEffect(()=>{if(focusReader.current&&!fullWidthTools){focusReader.current=false;toolsButton.current?.focus({preventScroll:true})}if(focusTool.current&&!collapsed){const index=toolTabs.findIndex(([id])=>id===focusTool.current);toolButtons.current[index]?.focus({preventScroll:true});focusTool.current=undefined}});
 useEffect(()=>{if(!focused)return;const escape=(event:globalThis.KeyboardEvent)=>{if(event.key!=='Escape'||event.defaultPrevented||document.fullscreenElement||(event.target instanceof Element&&event.target.closest('input,textarea,select,[role="combobox"],[role="dialog"]')))return;event.preventDefault();changeFocus(false);focusButton.current?.focus({preventScroll:true})};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape)},[focused]);
 // The first render uses a provisional height; restore again after measuring,
 // otherwise the browser can clamp a near-bottom position to the old maximum.
 useLayoutEffect(()=>{const pane=panels.current[tab];if(pane&&!fullWidthTools)pane.scrollTop=scene.current.scroll[tab]||0},[tab,bounds.height,fullWidthTools]);
 useLayoutEffect(()=>{if(!focusResources)return;select('practice');const frame=requestAnimationFrame(()=>{const pane=panels.current.practice,resource=pane?.querySelector<HTMLDetailsElement>('#kw-learning-resources');if(pane&&resource){resource.open=true;pane.scrollTop+=resource.getBoundingClientRect().top-pane.getBoundingClientRect().top}});return()=>cancelAnimationFrame(frame)},[focusResources]);
 const jump=(id:string)=>{const pane=panels.current.lesson,target=pane?.querySelector<HTMLElement>('#'+id);if(pane&&target){pane.scrollTop+=target.getBoundingClientRect().top-pane.getBoundingClientRect().top-12;target.focus({preventScroll:true})}};
 function keyboard(event:React.KeyboardEvent,index:number,count:number,choose:(index:number)=>void){let next=index;if(event.key==='ArrowRight')next=(index+1)%count;else if(event.key==='ArrowLeft')next=(index+count-1)%count;else if(event.key==='Home')next=0;else if(event.key==='End')next=count-1;else return;event.preventDefault();choose(next)}
 return <div className={'kw-learning-workspace'+(focused?' is-focused':'')+(collapsed?' is-tools-collapsed':'')+(fullWidthTools?' is-tools-full-width':'')+(resizing?' is-resizing-tools':'')} ref={root} style={{height:bounds.height,'--kw-learning-tool-width':toolWidth+'px'} as CSSProperties}>
  <section className="kw-learning-reader" aria-label="学习阅读区" hidden={fullWidthTools}>
   <div className="kw-learning-reader-bar">
    <div className="kw-learning-reader-tabs" role="tablist" aria-label="学习阅读分区">{readTabs.map(([id,label],index)=><button key={id} type="button" role="tab" id={'kw-learning-read-'+id+'-tab'} aria-controls={'kw-learning-read-'+id+'-panel'} aria-selected={tab===id} tabIndex={tab===id?0:-1} ref={element=>{mainButtons.current[index]=element}} onClick={()=>select(id)} onKeyDown={event=>keyboard(event,index,readTabs.length,next=>{select(readTabs[next][0]);mainButtons.current[next]?.focus()})}>{label}</button>)}</div>
    {tab==='lesson'&&!!chapters.length&&<nav className="kw-learning-chapter-nav" aria-label="学习内容目录"><select aria-label="跳转讲解章节" defaultValue="" onChange={event=>{if(event.target.value)jump(event.target.value);event.currentTarget.value=''}}><option value="">章节</option>{chapters.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></nav>}
    <div className="kw-learning-reader-actions"><button type="button" ref={focusButton} aria-pressed={focused} title={focused?'退出专注阅读（Esc）':'专注阅读，保留当前阅读位置'} onClick={()=>changeFocus(!focused)}>{focused?'退出专注阅读':'专注阅读'}</button><button type="button" ref={toolsButton} aria-expanded={!collapsed} aria-controls="kw-learning-tool-dock" onClick={()=>collapsed?openTool(tool):closeTools()}>{collapsed?'展开工具':'收起工具'}</button></div>
   </div>
   {readTabs.map(([id])=><section key={id} role="tabpanel" id={'kw-learning-read-'+id+'-panel'} aria-labelledby={'kw-learning-read-'+id+'-tab'} tabIndex={0} hidden={tab!==id} ref={element=>{if(element)panels.current[id]=element}} className="kw-learning-reader-scroll" onScroll={event=>{if(tab===id&&!fullWidthTools){scene.current.scroll[id]=event.currentTarget.scrollTop;persist()}}}>
    <div className="kw-learning-pane-content">{visited.has(id)?id==='lesson'?lesson:id==='evidence'?evidence:practice:null}</div>
   </section>)}
  </section>
  <div className="kw-learning-tool-resizer" role="separator" aria-label="调整学习工具宽度" aria-orientation="vertical" aria-valuemin={280} aria-valuemax={maxWidth} aria-valuenow={toolWidth} aria-valuetext={toolWidth+'像素'} tabIndex={0} hidden={collapsed||fullWidthTools} title="拖动调整工具宽度；方向键微调，双击恢复默认"
   onDoubleClick={resetWidth}
   onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture?.(event.pointerId);dragging.current={pointerId:event.pointerId,x:event.clientX,width:toolWidth};setResizing(true)}}
   onPointerMove={event=>{const drag=dragging.current;if(!drag||drag.pointerId!==event.pointerId)return;resize(drag.width+drag.x-event.clientX,false)}}
   onPointerUp={finishResize} onPointerCancel={finishResize} onLostPointerCapture={finishResize}
   onKeyDown={event=>{const step=event.shiftKey?48:16;let next:number;if(event.key==='ArrowLeft')next=toolWidth+step;else if(event.key==='ArrowRight')next=toolWidth-step;else if(event.key==='Home')next=280;else if(event.key==='End')next=maxWidth;else if(event.key==='Enter'){event.preventDefault();resetWidth();return}else return;event.preventDefault();resize(next)}}><span aria-hidden="true"/></div>
  <aside id="kw-learning-tool-dock" className="kw-learning-tool-dock" aria-label="随手学习工具" hidden={collapsed}>
   {fullWidthTools&&<button type="button" className="kw-learning-return-reader" onClick={closeTools}>返回学习正文</button>}
   <LearningProgress variant="dock" projectId={projectId} nodeId={nodeId} onNode={onNode} summaryVisible={!collapsed&&tool==='records'} onOpenSummary={()=>openTool('records')}>
    <div role="tablist" aria-label="随手学习工具分区" className="kw-learning-tool-tabs">{toolTabs.map(([id,label],index)=><button key={id} type="button" role="tab" id={'kw-learning-tool-'+id+'-tab'} aria-controls={'kw-learning-tool-'+id+'-panel'} aria-selected={tool===id} tabIndex={tool===id?0:-1} ref={element=>{toolButtons.current[index]=element}} onClick={()=>onTool(id)} onKeyDown={event=>keyboard(event,index,toolTabs.length,next=>{onTool(toolTabs[next][0]);toolButtons.current[next]?.focus()})}>{label}</button>)}</div>
    <section className="kw-learning-tool-panel" role="tabpanel" id="kw-learning-tool-question-panel" aria-labelledby="kw-learning-tool-question-tab" hidden={tool!=='question'}>{question}</section>
    <section className="kw-learning-tool-panel" role="tabpanel" id="kw-learning-tool-notes-panel" aria-labelledby="kw-learning-tool-notes-tab" hidden={tool!=='notes'}>{notes}</section>
   </LearningProgress>
  </aside>
  <aside className="kw-learning-tool-rail" aria-label="学习工具快捷入口" hidden={!collapsed}><button type="button" aria-label="打开提问工具" onClick={()=>openTool('question')}>提问</button><button type="button" aria-label="打开笔记工具" onClick={()=>openTool('notes')}>笔记</button><button type="button" aria-label="查看学习小结" onClick={()=>openTool('records')}>小结</button></aside>
 </div>;
}

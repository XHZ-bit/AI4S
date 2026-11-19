import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Button,theme as antdTheme} from 'antd';
import {MinusOutlined,PlusOutlined,FullscreenOutlined} from '@ant-design/icons';
import ForceGraph2D from 'react-force-graph-2d';
import type {KnowledgeEdge,KnowledgeGraph,KnowledgeNode} from '../../api/knowledge';
import {nodeKindLabels} from '../../api/knowledge';
import {useCurrentAccount} from '../SessionContext';
import {canvasTooltip,drawForceNode} from './forceNodeDrawing';
import './project-force-graph.css';

type Point={x:number;y:number};
interface NetworkScene {positions:Record<string,Point>;camera?:Point&{zoom:number}}
type NetworkNode=KnowledgeNode&{x?:number;y?:number;fx?:number;fy?:number};
const LIGHT:Record<string,string>={concept:'#438e64',method:'#3884ce',formula:'#a76d37',module:'#4b9187',algorithm:'#6c72ae',experiment:'#b47a44',finding:'#8d66a1',paper:'#378c98',report:'#47858e',code:'#8c69af',problem:'#a47548'};
const DARK:Record<string,string>={concept:'#74b98d',method:'#78a8df',formula:'#d6ac72',module:'#7cbdb0',algorithm:'#a6a9d7',experiment:'#d7ac7d',finding:'#bba0d1',paper:'#73bdc5',report:'#84bac1',code:'#b8a0d5',problem:'#c6aa7e'};
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<1000000;
export const networkSceneKey=(account:string|undefined,project:string,scope:string)=>`paperstride:${account||'local'}:project-network:${project}:${scope}`;
export function readNetworkScene(key:string):NetworkScene{
 try{
  const raw=JSON.parse(localStorage.getItem(key)||'null');const positions:Record<string,Point>={};
  if(raw?.positions&&typeof raw.positions==='object')for(const [id,point] of Object.entries(raw.positions).slice(0,2000)){
   const value=point as Point;if(id.length<=250&&finite(value?.x)&&finite(value?.y))positions[id]={x:value.x,y:value.y};
  }
  const c=raw?.camera;
  return {positions,...(finite(c?.x)&&finite(c?.y)&&finite(c?.zoom)&&c.zoom>=.1&&c.zoom<=12?{camera:{x:c.x,y:c.y,zoom:c.zoom}}:{})};
 }catch{return {positions:{}}}
}

/** The parent supplies project-scoped current records; this renderer makes no API request. */
export default function ProjectForceGraph({projectId,scope,graph,height,selectedNodeId,onNode,onEdge,onClear}:{projectId:string;scope:string;graph:KnowledgeGraph;height?:number;selectedNodeId?:string;onNode:(node:KnowledgeNode)=>void;onEdge:(edge:KnowledgeEdge)=>void;onClear?:()=>void}){
 const account=useCurrentAccount(),{token}=antdTheme.useToken();
 const key=networkSceneKey(account?.id,projectId,scope);
 const root=useRef<HTMLDivElement>(null),host=useRef<HTMLDivElement>(null),force=useRef<any>();
 const saved=useRef<{key:string;scene:NetworkScene}>({key,scene:readNetworkScene(key)});
 if(saved.current.key!==key)saved.current={key,scene:readNetworkScene(key)};
 const dark=token.colorBgContainer.toLowerCase()==='#212824'||document.documentElement.dataset.theme==='dark';
 const palette=dark?DARK:LIGHT;
 const [size,setSize]=useState({width:640,height:420}),[notice,setNotice]=useState('');
 const nodes=useRef(new Map<string,NetworkNode>()),initialized=useRef(false),restored=useRef(false),entry=useRef({key,camera:saved.current.scene.camera});
 if(entry.current.key!==key){nodes.current=new Map();initialized.current=false;restored.current=false;entry.current={key,camera:saved.current.scene.camera}}
 const current=useRef(graph);current.current=graph;
 const linksById=useMemo(()=>new Map(graph.edges.filter(edge=>edge.project_id===projectId).map(edge=>[edge.id,edge])),[graph.edges,projectId]);
 const data=useMemo(()=>{
  const allowed=new Set(graph.nodes.filter(node=>node.project_id===projectId).map(node=>node.id));
  const next=new Map<string,NetworkNode>();
  for(const original of graph.nodes){
   if(!allowed.has(original.id))continue;
   const previous=nodes.current.get(original.id),position=saved.current.scene.positions[original.id];
   const value=previous?Object.assign(previous,original,...(finite(previous.x)&&finite(previous.y)?[{fx:previous.x,fy:previous.y}]:[])):{...original,...(position?{x:position.x,y:position.y,fx:position.x,fy:position.y}:{})};
   next.set(value.id,value);
  }
  nodes.current=next;
  return {nodes:[...next.values()],links:graph.edges.filter(edge=>edge.project_id===projectId&&allowed.has(edge.source)&&allowed.has(edge.target)).map(edge=>({...edge,source:edge.source,target:edge.target}))};
 },[graph.nodes,graph.edges,projectId,key]);
 const persist=useCallback(()=>{
  if(saved.current.key!==key)return false;
  const positions:Record<string,Point>={...saved.current.scene.positions};for(const node of nodes.current.values())if(finite(node.x)&&finite(node.y))positions[node.id]={x:node.x,y:node.y};
  const center=force.current?.centerAt?.(),zoom=force.current?.zoom?.();
  const camera=center&&finite(center.x)&&finite(center.y)&&finite(zoom)?{x:center.x,y:center.y,zoom}:saved.current.scene.camera;
  const scene={positions,...(camera?{camera}:{})};saved.current.scene=scene;
  try{localStorage.setItem(key,JSON.stringify(scene));return true}catch{setNotice('网络布局未保存，可重试。');return false}
 },[key]);
 useEffect(()=>()=>{persist()},[persist]);
 useLayoutEffect(()=>{
  const element=host.current;if(!element)return;
  const measure=()=>{
   const bounds=element.getBoundingClientRect();const width=Math.max(1,Math.round(element.clientWidth||bounds.width||640));
   const nextHeight=height??Math.max(320,Math.min(900,Math.floor(window.innerHeight-Math.max(64,bounds.top)-82)));
   setSize(old=>old.width===width&&old.height===nextHeight?old:{width,height:nextHeight});
  };
  measure();const observer=new ResizeObserver(measure);observer.observe(element);window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure)};
 },[key,height]);
 useEffect(()=>{
  if(!data.nodes.length)return;
  force.current?.d3Force?.('charge')?.strength(-135);force.current?.d3Force?.('link')?.distance(76);
  const camera=entry.current.camera;
  if(camera&&!restored.current){restored.current=true;initialized.current=true;force.current?.centerAt?.(camera.x,camera.y,0);force.current?.zoom?.(camera.zoom,0)}
 },[data,key]);
 useEffect(()=>{force.current?.refresh?.()},[selectedNodeId,dark]);
 const choose=(id:string)=>{const original=current.current.nodes.find(node=>node.id===id&&node.project_id===projectId);if(original){initialized.current=true;onNode(original)}};
 const labelBoxes=useRef<{x:number;y:number;w:number;h:number}[]>([]);
 function resetLayout(){for(const node of nodes.current.values()){delete node.fx;delete node.fy}saved.current.scene={positions:{}};initialized.current=false;force.current?.d3ReheatSimulation?.();setNotice('已重新排列关系网络');}
 function zoomBy(factor:number){initialized.current=true;const value=force.current?.zoom?.();if(finite(value))force.current?.zoom?.(Math.max(.1,Math.min(12,value*factor)),150)}
 return <section className="kw-project-network" ref={root} aria-label="课题关系网络">
  <div className="kw-project-network-stage" ref={host} tabIndex={0} aria-label="课题关系网络画布" onPointerDown={()=>{initialized.current=true}} onWheelCapture={()=>{initialized.current=true}} onKeyDown={event=>{if(event.key==='Escape')onClear?.()}} style={{height:size.height}}>
   {data.nodes.length?<ForceGraph2D ref={force} width={size.width} height={size.height} graphData={data} nodeId="id" nodeLabel={(node:any)=>canvasTooltip(node.label)} backgroundColor={token.colorBgContainer} cooldownTicks={100} minZoom={.1} maxZoom={12} enableNodeDrag enablePanInteraction enableZoomInteraction
    onRenderFramePre={(ctx:CanvasRenderingContext2D,scale:number)=>{
     labelBoxes.current=[];const selected=nodes.current.get(selectedNodeId||'');
     if(!selected||!finite(selected.x)||!finite(selected.y))return;
     const zoom=scale>0?scale:1;ctx.save();ctx.font=`600 ${11/zoom}px sans-serif`;
     const label=selected.label.length>34?selected.label.slice(0,33)+'…':selected.label,w=ctx.measureText(label).width,padding=2/zoom;
     labelBoxes.current.push({x:selected.x-w/2-padding,y:selected.y+8-padding,w:w+2*padding,h:14/zoom+2*padding});ctx.restore();
    }}
    nodeCanvasObject={(node:any,ctx:CanvasRenderingContext2D,scale:number)=>{
     if(!Number.isFinite(node.x)||!Number.isFinite(node.y))return;
     const selected=node.id===selectedNodeId;drawForceNode(ctx,node,palette[node.kind]||palette.concept,node.kind==='paper'||node.kind==='report'?5:4,selected,!!selectedNodeId&&!selected);
     if(selected||data.nodes.length<=65||scale>1.6){
      ctx.save();ctx.font=`${selected?'600 ':''}${11/scale}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';
      const label=node.label.length>34?node.label.slice(0,33)+'…':node.label,w=ctx.measureText(label).width,h=14/scale;
      const box={x:node.x-w/2,y:node.y+8,w,h};
      if(selected||!labelBoxes.current.some(other=>box.x<other.x+other.w&&box.x+box.w>other.x&&box.y<other.y+other.h&&box.y+box.h>other.y)){
       ctx.fillStyle=selected?token.colorText:token.colorTextSecondary;ctx.fillText(label,node.x,node.y+8);labelBoxes.current.push(box);
      }ctx.restore();
     }
    }}
    nodePointerAreaPaint={(node:any,color:string,ctx:CanvasRenderingContext2D)=>{if(!finite(node.x)||!finite(node.y))return;ctx.fillStyle=color;ctx.beginPath();ctx.arc(node.x,node.y,11,0,Math.PI*2);ctx.fill()}}
    linkColor={(edge:any)=>selectedNodeId&&(typeof edge.source==='object'?edge.source.id:edge.source)!==selectedNodeId&&(typeof edge.target==='object'?edge.target.id:edge.target)!==selectedNodeId?token.colorBorderSecondary:token.colorTextTertiary}
    linkWidth={1} linkDirectionalArrowLength={4} linkDirectionalArrowRelPos={1} linkLabel={(edge:any)=>canvasTooltip(edge.label+(edge.explanation?' · '+edge.explanation:''))}
    onNodeClick={(node:any)=>choose(node.id)} onLinkClick={(edge:any)=>{const original=linksById.get(edge.id);if(original)onEdge(original)}} onBackgroundClick={onClear}
    onNodeDragEnd={(node:any)=>{node.fx=node.x;node.fy=node.y;persist()}}
    onZoomEnd={()=>persist()}
    onEngineStop={()=>{if(!initialized.current){initialized.current=true;force.current?.zoomToFit?.(0,45);const value=force.current?.zoom?.();if(finite(value)&&value>2)force.current?.zoom?.(2,0)}persist()}}
   />:<p className="kw-project-network-empty">当前范围还没有知识节点，可新增节点或导入资料。</p>}
  </div>
  <div className="kw-project-network-controls">
   <label>定位节点<select aria-label="定位关系网络节点" value={selectedNodeId||''} onChange={event=>{const id=event.target.value;if(!id)return;choose(id);const point=nodes.current.get(id);if(finite(point?.x)&&finite(point?.y))force.current?.centerAt?.(point.x,point.y,180)}}><option value="">选择一个节点</option>{data.nodes.map(node=><option key={node.id} value={node.id}>{node.label} · {nodeKindLabels[node.kind]||node.kind}</option>)}</select></label>
   <span>{data.nodes.length} 个节点 · {data.links.length} 条关系</span>
   <div><Button size="small" aria-label="缩小关系网络" icon={<MinusOutlined/>} onClick={()=>zoomBy(1/1.2)}/><Button size="small" onClick={()=>{initialized.current=true;force.current?.zoomToFit?.(150,45)}}>适应画布</Button><Button size="small" aria-label="放大关系网络" icon={<PlusOutlined/>} onClick={()=>zoomBy(1.2)}/><Button size="small" type="text" onClick={resetLayout}>重新布局</Button><Button size="small" aria-label="展开关系网络" icon={<FullscreenOutlined/>} onClick={()=>host.current?.requestFullscreen?.()}/></div>
  </div>
  {notice&&<p role="status" className="kw-project-network-notice">{notice}</p>}
 </section>;
}

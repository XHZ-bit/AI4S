import {NODE_HEIGHT,NODE_WIDTH,type GraphLayout} from './KnowledgeGraphLayout';

export interface NodePosition {x:number;y:number}
export type NodePositions=Record<string,NodePosition>;
export type ScopedNodePositions=Record<string,NodePositions>;
const MAX_COORDINATE=10000;
const bound=(value:number)=>Math.max(16,Math.min(MAX_COORDINATE,value));

/** Layout is personal browser state; ignore corrupt or foreign-project entries. */
export function restoreNodeLayouts(value:unknown,projectId:string):ScopedNodePositions {
 if(!value||typeof value!=='object'||Array.isArray(value))return {};
 const result:ScopedNodePositions={};
 for(const [scope,raw] of Object.entries(value).filter(([key])=>key.startsWith(projectId+'/')).slice(-40)){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))continue;
  const positions:NodePositions={};
  for(const [id,point] of Object.entries(raw).slice(0,2000)){
   if(!point||typeof point!=='object')continue;
   const {x,y}=point as NodePosition;
   if(Number.isFinite(x)&&Number.isFinite(y))positions[id]={x:bound(x),y:bound(y)};
  }
  if(Object.keys(positions).length)result[scope]=positions;
 }
 return result;
}

export function dragPosition(start:NodePosition,dx:number,dy:number,zoom:number):NodePosition {
 const scale=Number.isFinite(zoom)&&zoom>0?zoom:1;
 return {x:bound(start.x+dx/scale),y:bound(start.y+dy/scale)};
}

/** User coordinates override automatic coordinates without mutating the base layout. */
export function applyNodePositions(base:GraphLayout,positions:NodePositions):GraphLayout {
 const points=new Map(base.points);
 for(const [id,point] of Object.entries(positions)){
  const original=points.get(id);
  if(original&&Number.isFinite(point.x)&&Number.isFinite(point.y))points.set(id,{...original,x:bound(point.x),y:bound(point.y)});
 }
 return {...base,points,width:Math.max(base.width,...[...points.values()].map(p=>p.x+NODE_WIDTH+36)),height:Math.max(base.height,...[...points.values()].map(p=>p.y+NODE_HEIGHT+36))};
}

/** Find the nearest available drop location so one card cannot conceal another. */
export function resolveNodeDrop(layout:GraphLayout,id:string,desired:NodePosition):NodePosition {
 const other=[...layout.points].filter(([key])=>key!==id).map(([,p])=>p);
 const clear=(p:NodePosition)=>other.every(q=>p.x+NODE_WIDTH+20<=q.x||q.x+NODE_WIDTH+20<=p.x||p.y+NODE_HEIGHT+20<=q.y||q.y+NODE_HEIGHT+20<=p.y);
 const point={x:bound(desired.x),y:bound(desired.y)};
 if(clear(point))return point;
 const xs=new Set([point.x,16,...other.flatMap(p=>[bound(p.x-NODE_WIDTH-24),bound(p.x+NODE_WIDTH+24)])]);
 const ys=new Set([point.y,16,...other.flatMap(p=>[bound(p.y-NODE_HEIGHT-24),bound(p.y+NODE_HEIGHT+24)])]);
 const candidates=[...xs].flatMap(x=>[...ys].map(y=>({x,y}))).filter(clear);
 candidates.sort((a,b)=>Math.hypot(a.x-point.x,a.y-point.y)-Math.hypot(b.x-point.x,b.y-point.y));
 return candidates[0]||point;
}

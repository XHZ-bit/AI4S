import type {KnowledgeEdge,KnowledgeGraph,KnowledgeNode} from '../../api/knowledge';

export const NODE_WIDTH=232,NODE_HEIGHT=100;
export function wrapNodeLabel(label:string,maximum=28){
 const width=(value:string)=>Array.from(value).reduce((sum,char)=>sum+(char.charCodeAt(0)>255?2:1),0);
 const lines:string[]=[];let line='';
 for(const token of label.match(/[A-Za-z0-9][A-Za-z0-9_./:+-]*|[^\x00-\xff]|\s+|./gu)||[]){
  if(!line&&/^\s+$/.test(token))continue;
  if(width(token)>maximum){for(const char of token){if(width(line+char)>maximum){lines.push(line.trim());line=''}line+=char}continue}
  if(width(line+token)>maximum){lines.push(line.trim());line=token.trimStart()}else line+=token;
 }
 if(line.trim())lines.push(line.trim());
 if(lines.length<=2)return lines;
 let last=lines[1];
 if(width(last)>maximum-2){const words=last.match(/^(.*)\s+\S+$/);last=words?words[1]:Array.from(last).slice(0,-1).join('')}
 return [lines[0],last+'…'];
}
const roots=new Set(['paper','report','results','code']);
const priority:Record<string,number>={method:0,module:1,problem:2,algorithm:3,concept:4,formula:5,finding:6,experiment:7,contribution:8};
const rank=(node:KnowledgeNode)=>(node.metadata?.semantic?0:20)+(priority[node.kind]??12);

/** Space -> material is the only browse hierarchy. Details stay directly reachable. */
export function selectGraphScene(graph:KnowledgeGraph,sourceId?:string,focus?:string,maximum=16){
 const center=graph.nodes.find(n=>n.id===focus)||(sourceId?graph.nodes.find(n=>n.source_id===sourceId&&!n.parent_id):undefined);
 maximum=Math.min(maximum,center||sourceId?16:14);
 const chosen:KnowledgeNode[]=[],visibleKeys=new Set<string>();
 const byId=new Map(graph.nodes.map(n=>[n.id,n]));
 const related=new Map<string,Map<string,number>>();
 for(const edge of graph.edges){
  if(['CONTAINS','MENTIONS','PREREQUISITE_OF','PREREQUISITE_FOR'].includes(edge.kind))continue;
  const a=byId.get(edge.source),b=byId.get(edge.target);
  if(!a?.metadata?.semantic||!b?.metadata?.semantic)continue;
  for(const [current,neighbor] of [[a,b],[b,a]]){
   const connections=related.get(current.id)||new Map<string,number>();
   const weight=(['method','module'].includes(neighbor.kind)?4:1)+(edge.evidence_ids.length?3:0);
   connections.set(neighbor.id,Math.max(connections.get(neighbor.id)||0,weight));related.set(current.id,connections);
  }
 }
 const relevance=(node:KnowledgeNode)=>[...(related.get(node.id)?.values()||[])].reduce((sum,value)=>sum+value,0);
 const byRelevance=(nodes:KnowledgeNode[])=>[...nodes].sort((a,b)=>rank(a)-rank(b)||relevance(b)-relevance(a)||a.label.localeCompare(b.label));
 // Repeated extraction records remain in the detail list; identical labels do not occupy two diagram slots.
 const add=(node?:KnowledgeNode)=>{
  if(!node||chosen.length>=maximum||chosen.some(n=>n.id===node.id))return false;
  const key=node.kind+'\0'+node.label.trim()+'\0'+(node.parent_id||'');
  if(visibleKeys.has(key))return false;
  chosen.push(node);visibleKeys.add(key);return true;
 };
 if(center||sourceId){
  add(center);
  let candidates=graph.nodes.filter(n=>n.id!==center?.id);
  if(focus&&center){
   const context=new Set([center.id]);
   for(let depth=0;depth<2;depth++){
    const previous=new Set(context);
    for(const edge of graph.edges)if(previous.has(edge.source)||previous.has(edge.target)){context.add(edge.source);context.add(edge.target)}
    for(const n of graph.nodes)if(n.parent_id&&previous.has(n.parent_id))context.add(n.id);
   }
   candidates=candidates.filter(n=>context.has(n.id)||!n.parent_id&&n.source_id===center.source_id);
  }
  // Reserve room for modules as well as methods; a long problem list must not consume the view.
  const pools=new Map<string,KnowledgeNode[]>();
  for(const n of byRelevance(candidates)){const pool=pools.get(n.kind)||[];pool.push(n);pools.set(n.kind,pool)}
  const take=(kind:string,count:number)=>{let accepted=0;const pool=pools.get(kind)||[];while(pool.length&&accepted<count&&chosen.length<maximum)if(add(pool.shift()))accepted++};
  take('method',4);take('module',5);
  for(const kind of ['problem','contribution','finding','formula','concept','experiment','algorithm'])take(kind,1);
  for(const n of byRelevance(candidates))add(n);
 }else{
  const groups=new Map<string,KnowledgeNode[]>();
  for(const n of graph.nodes){const group=groups.get(n.source_id)||[];group.push(n);groups.set(n.source_id,group)}
  const all=[...groups.values()].sort((a,b)=>Number(!a.some(n=>!n.parent_id&&['paper','report'].includes(n.kind)))-Number(!b.some(n=>!n.parent_id&&['paper','report'].includes(n.kind))));
  const primary=all.filter(group=>group.some(n=>!n.parent_id&&['paper','report'].includes(n.kind)));
  const selectedGroups=(primary.length?primary:all).slice(0,7);
  // Keep materials and their key methods together, so opening a paper takes a single click.
  for(const group of selectedGroups)add(group.find(n=>!n.parent_id&&roots.has(n.kind)));
  for(const group of selectedGroups)add(byRelevance(group.filter(n=>n.parent_id&&['method','module','problem'].includes(n.kind)))[0]);
  for(const n of byRelevance(selectedGroups.flat()).filter(n=>!roots.has(n.kind)))add(n);
 }
 const nodes=chosen.slice(0,maximum),ids=new Set(nodes.map(n=>n.id));
 return {graph:{...graph,nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))},center,
  omitted:graph.nodes.filter(n=>!ids.has(n.id))};
}

export interface Point{x:number;y:number;depth:number}
export interface GraphLayout{points:Map<string,Point>;lanes:{kind:number;label:string;x:number;count:number}[];width:number;height:number;hub:{x:number;y:number};centerId?:string}
export function layoutFocusGraph(graph:KnowledgeGraph,centerId?:string,_narrow=false):GraphLayout{
 const points=new Map<string,Point>(),columnCount=_narrow?1:graph.nodes.length<=6?2:3,capacity=Math.ceil(graph.nodes.length/columnCount);
 const groups:KnowledgeNode[][]=Array.from({length:columnCount},()=>[]);
 const preferred=(n:KnowledgeNode)=>!n.parent_id&&roots.has(n.kind)||['problem','contribution','hypothesis'].includes(n.kind)?0:['method','algorithm'].includes(n.kind)?Math.min(1,columnCount-1):columnCount-1;
 for(const n of [...graph.nodes].sort((a,b)=>Number(b.id===centerId)-Number(a.id===centerId)||preferred(a)-preferred(b)||rank(a)-rank(b))){
  const ideal=preferred(n),choices=[ideal,...Array.from({length:columnCount},(_,i)=>i).filter(i=>i!==ideal).sort((a,b)=>groups[a].length-groups[b].length)];
  const index=choices.find(i=>groups[i].length<capacity)??choices[0];groups[index].push(n);
 }
 // Barycentric ordering aligns actual neighbours, without inventing parent links.
 for(let pass=0;pass<2;pass++)for(let column=1;column<groups.length;column++){
  const previous=new Map(groups.slice(0,column).flatMap(group=>group.map((n,i)=>[n.id,i] as const)));
  const weight=(node:KnowledgeNode)=>{const linked=graph.edges.filter(e=>e.source===node.id||e.target===node.id).flatMap(e=>[e.source,e.target]).filter(id=>previous.has(id));return linked.length?linked.reduce((s,id)=>s+previous.get(id)!,0)/linked.length:999};
  groups[column].sort((a,b)=>weight(a)-weight(b)||rank(a)-rank(b)||a.label.localeCompare(b.label));
 }
 const lanes=groups.map((group,column)=>({kind:column,label:column===0?'研究上下文':column===1?'方法与关联':'实现与依据',x:36+column*370,count:group.length}));
 groups.forEach((group,column)=>group.forEach((node,row)=>points.set(node.id,{x:36+column*370,y:48+row*130,depth:column})));
 return {points,lanes,width:columnCount===1?304:columnCount===2?760:1136,height:Math.max(410,48+capacity*130-30+32),hub:{x:36,y:48},centerId};
}

type XY={x:number;y:number};
export interface Box{x:number;y:number;width:number;height:number}
export interface EdgeRoute{edge:KnowledgeEdge;points:XY[];d:string}
const overlaps=(a:Box,b:Box)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
export const graphBoxes=(layout:GraphLayout)=>[...layout.points.values()].map(p=>({...p,width:NODE_WIDTH,height:NODE_HEIGHT}));
const paddedBoxes=(layout:GraphLayout)=>graphBoxes(layout).map(b=>({x:b.x-12,y:b.y-12,width:b.width+24,height:b.height+24}));
function segmentClear(a:XY,b:XY,boxes:Box[]){
 return boxes.every(box=>a.x===b.x?!(a.x>box.x&&a.x<box.x+box.width&&Math.max(a.y,b.y)>box.y&&Math.min(a.y,b.y)<box.y+box.height):
  !(a.y>box.y&&a.y<box.y+box.height&&Math.max(a.x,b.x)>box.x&&Math.min(a.x,b.x)<box.x+box.width));
}
function clean(points:XY[]){
 const result:XY[]=[];
 for(const p of points){const last=result[result.length-1];if(last&&p.x===last.x&&p.y===last.y)continue;result.push(p);while(result.length>=3){const a=result[result.length-3],b=result[result.length-2],c=result[result.length-1];if((a.x===b.x&&b.x===c.x)||(a.y===b.y&&b.y===c.y))result.splice(result.length-2,1);else break}}
 return result;
}
const length=(a:XY,b:XY)=>Math.abs(a.x-b.x)+Math.abs(a.y-b.y);
function congestion(a:XY,b:XY,used:[XY,XY][]){
 let cost=0;
 for(const [c,d] of used){
  if(a.x===b.x&&c.x===d.x&&a.x===c.x||a.y===b.y&&c.y===d.y&&a.y===c.y){const amount=a.x===b.x?Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y))-Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y)):Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x))-Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x));if(amount>0)cost+=24+amount*.12}
  else if(a.x===b.x&&c.y===d.y&&a.x>Math.min(c.x,d.x)&&a.x<Math.max(c.x,d.x)&&c.y>Math.min(a.y,b.y)&&c.y<Math.max(a.y,b.y)||a.y===b.y&&c.x===d.x&&c.x>Math.min(a.x,b.x)&&c.x<Math.max(a.x,b.x)&&a.y>Math.min(c.y,d.y)&&a.y<Math.max(c.y,d.y))cost+=45;
 }
 return cost;
}
/** Orthogonal visibility grid: all node bodies have a 12px exclusion area. */
function gridPath(start:XY,end:XY,boxes:Box[],layout:GraphLayout,used:[XY,XY][]){
 const xs=[...new Set([12,layout.width-12,start.x,end.x,...boxes.flatMap(b=>[b.x-3,b.x+b.width+3])])].sort((a,b)=>a-b);
 const ys=[...new Set([12,layout.height-12,start.y,end.y,...boxes.flatMap(b=>[b.y-3,b.y+b.height+3])])].sort((a,b)=>a-b);
 const xIndex=new Map(xs.map((x,i)=>[x,i])),yIndex=new Map(ys.map((y,i)=>[y,i])),width=xs.length;
 const id=(x:number,y:number,d:number)=>(y*width+x)*3+d;
 const origin=id(xIndex.get(start.x)!,yIndex.get(start.y)!,0),targetCell=yIndex.get(end.y)!*width+xIndex.get(end.x)!;
 const distances=new Map([[origin,0]]),parents=new Map<number,number>(),queue:[number,number][]=[[origin,length(start,end)]];
 while(queue.length){
  let best=0;for(let i=1;i<queue.length;i++)if(queue[i][1]<queue[best][1])best=i;
  const [current]=queue.splice(best,1)[0],cell=Math.floor(current/3),direction=current%3,x=cell%width,y=Math.floor(cell/width),a={x:xs[x],y:ys[y]};
  if(cell===targetCell){const path=[a];let key=current;while(parents.has(key)){key=parents.get(key)!;const k=Math.floor(key/3);path.push({x:xs[k%width],y:ys[Math.floor(k/width)]})}return clean(path.reverse())}
  for(const [nx,ny,nd] of [[x-1,y,1],[x+1,y,1],[x,y-1,2],[x,y+1,2]]){
   if(nx<0||nx>=xs.length||ny<0||ny>=ys.length)continue;
   const b={x:xs[nx],y:ys[ny]};if(!segmentClear(a,b,boxes))continue;
   const next=id(nx,ny,nd),distance=distances.get(current)!+length(a,b)+(direction&&direction!==nd?20:0)+congestion(a,b,used);
   if(distance>=(distances.get(next)??Infinity))continue;
   distances.set(next,distance);parents.set(next,current);queue.push([next,distance+length(b,end)]);
  }
 }
 return undefined;
}
type Side='left'|'right'|'top'|'bottom';
const facing=(a:Point,b:Point):Side=>a.x===b.x?(b.y>a.y?'bottom':'top'):(b.x>a.x?'right':'left');
function port(point:Point,side:Side,part:number){
 const t=.18+part*.64;
 const p=side==='left'?{x:point.x,y:point.y+NODE_HEIGHT*t}:side==='right'?{x:point.x+NODE_WIDTH,y:point.y+NODE_HEIGHT*t}:side==='top'?{x:point.x+NODE_WIDTH*t,y:point.y}:{x:point.x+NODE_WIDTH*t,y:point.y+NODE_HEIGHT};
 const outside={x:p.x+(side==='left'?-15:side==='right'?15:0),y:p.y+(side==='top'?-15:side==='bottom'?15:0)};
 return {p,outside};
}
export function routeGraphEdges(graph:KnowledgeGraph,layout:GraphLayout):EdgeRoute[]{
 const boxes=paddedBoxes(layout),used:[XY,XY][]=[],orderedEdges=[...graph.edges].sort((a,b)=>a.id.localeCompare(b.id));
 const ends=new Map<string,{side:Side;part:number}>(),byPort=new Map<string,string[]>();
 for(const edge of orderedEdges){const a=layout.points.get(edge.source),b=layout.points.get(edge.target);if(!a||!b)continue;for(const [suffix,nodeId,side] of [['s',edge.source,facing(a,b)],['t',edge.target,facing(b,a)]] as const){const key=edge.id+':'+suffix,group=nodeId+':'+side;ends.set(key,{side,part:.5});const list=byPort.get(group)||[];list.push(key);byPort.set(group,list)}}
 for(const list of byPort.values())list.forEach((key,index)=>{ends.get(key)!.part=(index+1)/(list.length+1)});
 return orderedEdges.flatMap(edge=>{
  const a=layout.points.get(edge.source),b=layout.points.get(edge.target);if(!a||!b)return [];
  const ap=ends.get(edge.id+':s')!,bp=ends.get(edge.id+':t')!,start=port(a,ap.side,ap.part),end=port(b,bp.side,bp.part);
  const middle=gridPath(start.outside,end.outside,boxes,layout,used);
  // Layout points never overlap; their free perimeter grid therefore always has a route.
  if(!middle)throw new Error('No safe route for knowledge relation '+edge.id);
  const points=clean([start.p,...middle,end.p]);
  points.forEach((p,i)=>{if(i)used.push([points[i-1],p])});
  return [{edge,points,d:points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' ')}];
 });
}
function shortLabel(label:string){
 let text='',width=0;for(const character of Array.from(label)){const size=character.charCodeAt(0)>255?10.5:6;if(width+size>112)return {text:text+'…',width:width+12};text+=character;width+=size}return {text,width};
}
export function placeEdgeLabels(routes:EdgeRoute[],layout:GraphLayout,visibleIds:Set<string>){
 const labels=new Map<string,Box&{text:string}>(),occupied=graphBoxes(layout).map(b=>({x:b.x-8,y:b.y-8,width:b.width+16,height:b.height+16}));
 for(const route of routes){if(!visibleIds.has(route.edge.id))continue;const label=shortLabel(route.edge.label),width=label.width+12,height=22;
  const candidates=route.points.slice(1).map((p,i)=>({a:route.points[i],b:p})).sort((a,b)=>(b.a.y===b.b.y?1000:0)+Math.abs(b.a.x-b.b.x)+Math.abs(b.a.y-b.b.y)-(a.a.y===a.b.y?1000:0)-Math.abs(a.a.x-a.b.x)-Math.abs(a.a.y-a.b.y));
  for(const {a,b} of candidates){
   if(a.y===b.y&&Math.abs(a.x-b.x)<width+6)continue;
   if(a.x===b.x&&Math.abs(a.y-b.y)<height+6)continue;
   const box={x:(a.x+b.x)/2-width/2,y:(a.y+b.y)/2-height/2,width,height};
   if(box.x<0||box.y<0||box.x+width>layout.width||box.y+height>layout.height||occupied.some(other=>overlaps(box,other)))continue;
   labels.set(route.edge.id,{...box,text:label.text});occupied.push({...box,x:box.x-5,y:box.y-5,width:width+10,height:height+10});break;
  }
 }
 return labels;
}

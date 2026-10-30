import {expect,test} from 'vitest';
import type {KnowledgeGraph,KnowledgeNode} from '../api/knowledge';
import {graphBoxes,layoutFocusGraph,placeEdgeLabels,routeGraphEdges,selectGraphScene,wrapNodeLabel,NODE_WIDTH,NODE_HEIGHT} from '../components/knowledge/KnowledgeGraphLayout';

const node=(id:string,kind='module',extra:Partial<KnowledgeNode>={}):KnowledgeNode=>({id,kind,label:'A long current research topic '+id,project_id:'p',source_id:'s',parent_id:'root',summary:'Actual source context',origin:'source',research_status:'unknown',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{semantic:true},...extra});
const graph=(nodes:KnowledgeNode[],edges:KnowledgeGraph['edges']=[]):KnowledgeGraph=>({nodes,edges,total_nodes:nodes.length,total_edges:edges.length,truncated:false});
const overlap=(a:{x:number;y:number;width:number;height:number},b:{x:number;y:number;width:number;height:number})=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;

test('English wraps at word boundaries while Chinese and a single long identifier remain readable',()=>{
 expect(wrapNodeLabel('configuration and observation space')).toEqual(['configuration and','observation space']);
 expect(wrapNodeLabel('状态条件门控与有界跨分支信息交互方法').length).toBe(2);
 expect(wrapNodeLabel('exceptionally_long_unbroken_identifier_name').length).toBe(2);
});

test('a large paper is a bounded first layer and every omitted record remains accessible',()=>{
 const input=graph([node('root','paper',{parent_id:null}),...Array.from({length:499},(_,i)=>node('n'+i,i<2?'method':i<5?'problem':'concept'))]);
 const scene=selectGraphScene(input,'s');
 expect(scene.center?.id).toBe('root');expect(scene.graph.nodes.length).toBe(16);expect(scene.omitted.length).toBe(484);
 expect(new Set([...scene.graph.nodes,...scene.omitted].map(n=>n.id)).size).toBe(500);
 expect(scene.graph.nodes.some(n=>n.kind==='method')).toBe(true);
 const layout=layoutFocusGraph(scene.graph,scene.center?.id);expect(layout.height).toBeLessThan(850);
 const boxes=graphBoxes(layout);boxes.forEach((box,i)=>boxes.slice(i+1).forEach(other=>expect(overlap(box,other)).toBe(false)));
});
test('space overview exposes materials and key methods together so a paper is one click away',()=>{
 const nodes=Array.from({length:5},(_,i)=>[node('root'+i,'paper',{parent_id:null,source_id:'s'+i}),node('method'+i,'method',{parent_id:'root'+i,source_id:'s'+i}),node('table'+i,'concept',{parent_id:'root'+i,source_id:'s'+i,metadata:{structural:true}})]).flat();
 const scene=selectGraphScene(graph(nodes));
 for(let i=0;i<5;i++)expect(scene.graph.nodes.some(n=>n.id==='method'+i)).toBe(true);
 for(let i=0;i<5;i++)expect(scene.graph.nodes.some(n=>n.id==='root'+i)).toBe(true);expect(scene.graph.nodes.length).toBeLessThanOrEqual(14);
});
test('mobile keeps material and module context available without forcing three-node browse steps',()=>{
 const input=graph([node('root','paper',{parent_id:null}),...Array.from({length:4},(_,i)=>node('method'+i,'method')),...Array.from({length:8},(_,i)=>node('module'+i))]);
 const scene=selectGraphScene(input,'s',undefined,6),layout=layoutFocusGraph(scene.graph,scene.center?.id,true);
 expect(scene.graph.nodes.length).toBe(6);expect(scene.graph.nodes.filter(n=>n.kind==='method').length).toBeGreaterThan(1);
 expect(layout.points.size).toBe(6);expect(layout.width).toBeLessThan(360);expect(layout.height).toBeLessThan(850);
 expect([...layout.points.values()].every(p=>p.x+NODE_WIDTH<=layout.width)).toBe(true);
});
test('method and module quotas remain visible alongside a large problem set',()=>{
 const input=graph([node('root','paper',{parent_id:null}),...Array.from({length:15},(_,i)=>node('problem'+i,'problem')),node('method','method'),node('module'),node('formula','formula')]);
 const scene=selectGraphScene(input,'s');
 expect(scene.graph.nodes.some(n=>n.id==='method')).toBe(true);expect(scene.graph.nodes.some(n=>n.id==='module')).toBe(true);expect(scene.graph.nodes.some(n=>n.id==='formula')).toBe(true);
});
test('a connected core method outranks isolated methods, reserves module space and avoids duplicate labels',()=>{
 const methods=Array.from({length:12},(_,i)=>node('isolated'+i,'method',{label:'A isolated method '+i}));
 const modules=Array.from({length:8},(_,i)=>node('module'+i,'module',{label:'Module '+i}));
 const core=node('core','method',{label:'Z central coordination'}),duplicate=node('core-duplicate','method',{label:core.label});
 const edges=modules.map((n,i)=>({id:'uses'+i,project_id:'p',source_id:'s',source:core.id,target:n.id,kind:'USES',label:'Uses module',explanation:'Source-supported relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}}));
 const input=graph([node('root','paper',{parent_id:null}),...methods,core,duplicate,...modules,...Array.from({length:15},(_,i)=>node('problem'+i,'problem'))],edges);
 const scene=selectGraphScene(input,'s');
 expect(scene.graph.nodes.some(n=>n.id==='core')).toBe(true);
 expect(scene.graph.nodes.filter(n=>n.kind==='method').length).toBeGreaterThanOrEqual(4);
 expect(scene.graph.nodes.filter(n=>n.kind==='module').length).toBeGreaterThanOrEqual(5);
 expect(scene.graph.nodes.filter(n=>n.kind==='method'&&n.label===core.label).length).toBe(1);
 expect(scene.omitted.some(n=>n.id==='core-duplicate')).toBe(true);
});
test('a selected theme includes two-hop knowledge instead of requiring another browse level',()=>{
 const input=graph([node('root','method',{parent_id:null}),node('direct'),node('deep','formula',{parent_id:'direct'})],[{id:'edge',project_id:'p',source_id:'s',source:'root',target:'direct',kind:'USES',label:'用于',explanation:'Source-grounded relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}}]);
 expect(selectGraphScene(input,undefined,'root').graph.nodes.map(n=>n.id)).toEqual(['root','direct','deep']);
});
test('reverse and same-layer edges avoid node bodies; visible labels collide with neither nodes nor labels',()=>{
 const nodes=Array.from({length:16},(_,i)=>node('n'+i));
 const edges=nodes.flatMap(a=>nodes.filter(b=>a!==b).map(b=>({id:a.id+b.id,project_id:'p',source_id:'s',source:a.id,target:b.id,kind:'DEPENDS_ON',label:'用于当前任务的方法与实现比较',explanation:'Actual relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}})));
 const input=graph(nodes,edges),layout=layoutFocusGraph(input,'n0'),routes=routeGraphEdges(input,layout),boxes=graphBoxes(layout);
 expect(routes.length).toBe(edges.length);
 for(const route of routes)for(let i=1;i<route.points.length;i++){
  const a=route.points[i-1],b=route.points[i];expect(a.x===b.x||a.y===b.y).toBe(true);
  for(const box of boxes){const crosses=a.x===b.x?a.x>box.x&&a.x<box.x+box.width&&Math.max(a.y,b.y)>box.y&&Math.min(a.y,b.y)<box.y+box.height:a.y>box.y&&a.y<box.y+box.height&&Math.max(a.x,b.x)>box.x&&Math.min(a.x,b.x)<box.x+box.width;expect(crosses).toBe(false)}
 }
 const labels=[...placeEdgeLabels(routes,layout,new Set(edges.map(e=>e.id))).values()];expect(labels.length).toBeGreaterThan(0);
 labels.forEach((box,i)=>{for(const other of [...boxes,...labels.slice(i+1)])expect(overlap(box,other)).toBe(false)});
});

// Non-adjacent routes, including reverse directions, must preserve a 12px clear lane.
test('routes retain a safety margin around all unrelated nodes in realistic mixed layouts',()=>{
 for(const count of [3,6,10,16]){
  const nodes=Array.from({length:count},(_,i)=>node('n'+i,i===0?'paper':i%3===0?'method':'module',{parent_id:i===0?null:'n0'}));
  const edges=nodes.slice(1).flatMap((n,i)=>[{id:'forward'+i,project_id:'p',source_id:'s',source:'n0',target:n.id,kind:'USES',label:'用于',explanation:'Actual relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}},{id:'reverse'+i,project_id:'p',source_id:'s',source:n.id,target:'n0',kind:'SUPPORTS',label:'支持',explanation:'Actual relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}}]);
  const input=graph(nodes,edges),layout=layoutFocusGraph(input,'n0'),routes=routeGraphEdges(input,layout);
  expect(routes.length).toBe(edges.length);
  for(const route of routes)for(let i=1;i<route.points.length;i++)for(const [id,point] of layout.points){
   if(id===route.edge.source||id===route.edge.target)continue;
   const a=route.points[i-1],b=route.points[i],box={x:point.x-12,y:point.y-12,width:NODE_WIDTH+24,height:NODE_HEIGHT+24};
   const crosses=a.x===b.x?a.x>box.x&&a.x<box.x+box.width&&Math.max(a.y,b.y)>box.y&&Math.min(a.y,b.y)<box.y+box.height:a.y>box.y&&a.y<box.y+box.height&&Math.max(a.x,b.x)>box.x&&Math.min(a.x,b.x)<box.x+box.width;
   expect(crosses).toBe(false);
  }
 }
});

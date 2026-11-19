import type {KnowledgeEdge, KnowledgeGraph, KnowledgeNode} from '../../api/knowledge';

export interface RouteGraphStep {
 node_id:string;label:string;state:'todo'|'done'|'skipped';stale?:boolean;available?:boolean;
}
export interface RouteGraphInput {
 steps:RouteGraphStep[];graph:{nodes:KnowledgeNode[];edges:KnowledgeEdge[]};next_node_id?:string|null;
}

const active=(record:KnowledgeNode|KnowledgeEdge)=>!record.hidden&&!record.source_missing
 &&!['withdrawn','rejected','disputed'].includes(record.quality_status||'')&&!record.metadata?.source_withdrawn;

export function routeStepLabel(step:RouteGraphStep,nextNodeId?:string|null){
 return step.stale?'依据变化待复核':step.state==='done'?'已完成这一步':step.state==='skipped'?'已跳过':step.node_id===nextNodeId?'下一步':'待继续';
}

/** A personal order is not a semantic dependency. Retain only real current edges. */
export function selectSavedRouteGraph(route:RouteGraphInput):KnowledgeGraph {
 const nodesById=new Map(route.graph.nodes.filter(active).map(node=>[node.id,node]));
 const seen=new Set<string>(),nodes:KnowledgeNode[]=[];
 for(const step of route.steps){
  const node=nodesById.get(step.node_id);
  if(step.stale||step.available===false||!node||seen.has(node.id))continue;
  seen.add(node.id);nodes.push(node);
 }
 const edges=route.graph.edges.filter(edge=>active(edge)&&seen.has(edge.source)&&seen.has(edge.target));
 return {nodes,edges,total_nodes:nodes.length,total_edges:edges.length,truncated:false};
}

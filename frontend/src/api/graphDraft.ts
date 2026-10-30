/** Persist graph meaning, not d3 coordinates, velocities or canvas objects. */
export const GRAPH_DRAFT_LIMIT=89000;
const endpoint=(value:any)=>typeof value==='object'?value?.uid:value;
const text=(value:any,max=320)=>typeof value==='string'?value.slice(0,max):'';
const size=(raw:string)=>new TextEncoder().encode(raw).length;

function cleanGraph(graph:any,compact=false) {
 const nodes=(graph?.nodes||[]).slice(0,50).map((node:any)=>{
  const sources=new Map<string,any>();
  for(const source of node.sources||[]){if(!source.paper_uid)continue;const prior=sources.get(source.paper_uid);if(!prior)sources.set(source.paper_uid,{paper_uid:source.paper_uid,passage_id:source.passage_id||null,paper_title:text(source.paper_title,compact?80:240)});else if(!prior.passage_id&&source.passage_id)prior.passage_id=source.passage_id;}
  return {uid:node.uid,name:text(node.name,compact?80:320),type:node.type,available:node.available,is_match:node.is_match,identifier:text(node.identifier,150)||undefined,reason:text(node.reason,240)||undefined,year:node.year,
   sources:[...sources.values()].slice(0,compact?1:12),source_count:sources.size,
   access_links:compact?[]:(node.access_links||[]).slice(0,5).map((link:any)=>({url:link.url,label:text(link.label,100),origin:link.origin,note:text(link.note,160),verified_at:link.verified_at})),
   access_omitted:compact||!!node.access_omitted};
 });
 const ids=new Set(nodes.map((node:any)=>node.uid));
 const links=(graph?.links||[]).filter((link:any)=>ids.has(endpoint(link.source))&&ids.has(endpoint(link.target))).slice(0,150).map((link:any)=>({source:endpoint(link.source),target:endpoint(link.target),rel_type:link.rel_type,quality_status:link.quality_status,passage_id:link.passage_id,paper_uid:link.paper_uid}));
 return {nodes,links,selected_uid:graph?.selected_uid};
}

function pack(state:any) {
 const strings:string[]=[],indices=new Map<string,number>();
 const encode=(value:any):any=>{
  if(typeof value==='string'){let index=indices.get(value);if(index===undefined){index=strings.length;strings.push(value);indices.set(value,index);}return [index];}
  if(Array.isArray(value))return value.map(encode);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([,v])=>v!==undefined).map(([k,v])=>[k,encode(v)]));
  return value;
 };
 const payload=encode(state);return JSON.stringify({v:2,s:strings,p:payload});
}

export function serializeGraphDraft(state:{data:any;history:any[];query:string;type?:string;relation?:string;selected_uid?:string}) {
 const result={data:cleanGraph(state.data),history:(state.history||[]).slice(-10).map(graph=>cleanGraph(graph)),query:text(state.query,500),type:state.type,relation:state.relation,selected_uid:state.selected_uid};
 let raw=pack(result);
 // Drop oldest undo snapshots before reducing any current graph metadata.
 while(size(raw)>=GRAPH_DRAFT_LIMIT&&result.history.length){result.history.shift();raw=pack(result);}
 if(size(raw)>=GRAPH_DRAFT_LIMIT){result.data=cleanGraph(state.data,true);raw=pack(result);}
 // UIDs and locators are bounded by the graph/paper contracts. This final guard
 // protects against malformed imported data rather than sending an invalid body.
 if(size(raw)>=GRAPH_DRAFT_LIMIT)throw new Error('图谱标识内容超过可保存范围，请重新加载图谱');
 return raw;
}

export function restoreGraphDraft(raw:string) {
 const value=JSON.parse(raw);
 if(value.v!==2)return {...value,data:cleanGraph(value.data),history:(value.history||[]).slice(-10).map((graph:any)=>cleanGraph(graph))}; // Existing workspaces remain readable and bounded.
 if(!Array.isArray(value.s))throw new Error('Invalid graph draft');
 const decode=(item:any):any=>{
  if(Array.isArray(item)){if(item.length===1&&Number.isInteger(item[0]))return value.s[item[0]];return item.map(decode);}
  if(item&&typeof item==='object')return Object.fromEntries(Object.entries(item).map(([k,v])=>[k,decode(v)]));
  return item;
 };
 return decode(value.p);
}

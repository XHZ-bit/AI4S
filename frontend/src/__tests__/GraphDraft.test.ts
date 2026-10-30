import {serializeGraphDraft,restoreGraphDraft,GRAPH_DRAFT_LIMIT} from '../api/graphDraft';

function graph(version=0){
 const nodes=Array.from({length:50},(_,i)=>({uid:`node-${i}`,name:`论文及数据集 ${i} version ${version}`,type:i%2?'dataset':'paper',x:100,vy:2,index:i,sources:Array.from({length:8},(_,j)=>({paper_uid:`paper-${i}-${j}`,passage_id:`passage-${i}-${j}`,paper_title:`论文 ${i}-${j}`})),access_links:[{url:`https://publisher.example/data/${i}`,label:'官方项目入口',origin:'source_record'}]}));
 const links=Array.from({length:150},(_,i)=>({source:nodes[i%50],target:nodes[(i+1)%50],rel_type:'MENTIONS',paper_uid:`paper-${i%50}`,passage_id:`passage-${i}`,__indexColor:'transient'}));
 return {nodes,links};
}

test('graph drafts stay below the record limit and keep current source access and relations',()=>{
 const current=graph();(current.nodes[0] as any).__canvas=current;
 const raw=serializeGraphDraft({data:current,history:Array.from({length:10},(_,i)=>graph(i)),query:'dataset',type:'dataset'});
 expect(new TextEncoder().encode(raw).length).toBeLessThan(GRAPH_DRAFT_LIMIT);
 expect(raw).not.toContain('__canvas');expect(raw).not.toContain('__indexColor');
 const saved=restoreGraphDraft(raw);
 expect(saved.data.nodes.length).toBe(50);expect(saved.data.links.length).toBe(150);
 expect(saved.data.nodes[0].access_links[0].url).toBe('https://publisher.example/data/0');
 expect(saved.data.nodes[0].sources[0].paper_title).toBe('论文 0-0');
 expect(saved.data.nodes[0].x).toBeUndefined();
});

test('oversized display metadata is compacted after history while retaining source locators',()=>{
 const current=graph();
 current.nodes.forEach((node,i)=>{node.sources=Array.from({length:12},(_,j)=>({paper_uid:`p-${i}-${j}`,passage_id:`e-${i}-${j}`,paper_title:String(i+j)+'研究'.repeat(500)}));node.access_links=Array.from({length:5},(_,j)=>({url:'https://publisher.example/'+`${i}-${j}-`+'x'.repeat(1900),label:'资源链接',origin:'source_record'}));});
 const raw=serializeGraphDraft({data:current,history:[graph()],query:''});
 expect(new TextEncoder().encode(raw).length).toBeLessThan(GRAPH_DRAFT_LIMIT);
 const saved=restoreGraphDraft(raw);expect(saved.data.nodes.length).toBe(50);expect(saved.data.links.length).toBe(150);
 expect(saved.history.length).toBe(0);expect(saved.data.nodes[0].access_omitted).toBe(true);
 expect(saved.data.nodes[0].sources[0].paper_uid).toBe('p-0-0');
 expect(saved.data.nodes[0].sources[0].passage_id).toBe('e-0-0');
});

test('old drafts remain readable and duplicate paper references keep a usable passage',()=>{
 const old=graph();old.nodes[0].sources=[{paper_uid:'paper',passage_id:'',paper_title:'论文标题'},{paper_uid:'paper',passage_id:'located',paper_title:'论文标题'}];
 const saved=restoreGraphDraft(JSON.stringify({data:{...old,links:[]},history:[],query:'old'}));
 expect(saved.query).toBe('old');expect(saved.data.nodes[0].sources.length).toBe(1);
 expect(saved.data.nodes[0].sources[0].passage_id).toBe('located');
});

test('graph draft preserves selected node for current view and undo history',()=>{
 const current={nodes:graph().nodes.slice(0,6),links:[]};const previous={...current,selected_uid:'node-2'};
 const saved=restoreGraphDraft(serializeGraphDraft({data:current,history:[previous],query:'',selected_uid:'node-5'}));
 expect(saved.selected_uid).toBe('node-5');expect(saved.history[0].selected_uid).toBe('node-2');
});

import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import type {KnowledgeEdge,KnowledgeGraph,KnowledgeNode} from '../api/knowledge';
import type {SavedLearningRoute} from '../api/knowledgeRoutes';
import KnowledgeGraphView,{type GraphScene} from '../components/knowledge/KnowledgeGraph';
import {routeStepLabel,selectSavedRouteGraph} from '../components/knowledge/SavedRouteGraph';

const api=vi.hoisted(()=>({graph:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),getKnowledgeGraph:api.graph}));
vi.mock('../components/knowledge/NodeInspector',()=>({NodeInspector:()=>null,EdgeEditor:({edge}:{edge:KnowledgeEdge})=><p>检查关系 {edge.label}</p>}));
vi.mock('../components/knowledge/KnowledgePathPanel',()=>({default:()=>null}));

const node=(id:string):KnowledgeNode=>({id,project_id:'p',source_id:'s',kind:'concept',label:'知识'+id,summary:'独立知识说明',parent_id:'root',origin:'source',research_status:'reading',version:1,hidden:false,source_missing:false,evidence_ids:['e'+id],metadata:{semantic:true}});
const edge=(id:string,source:string,target:string,kind='DEPENDS_ON'):KnowledgeEdge=>({id,source,target,kind,label:'关系'+id,explanation:'实际保存的关系',project_id:'p',source_id:'s',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}});
const graph=(nodes:KnowledgeNode[],edges:KnowledgeEdge[]=[]):KnowledgeGraph=>({nodes,edges,total_nodes:nodes.length,total_edges:edges.length,truncated:false});
function route(nodes:KnowledgeNode[],edges:KnowledgeEdge[]=[]):SavedLearningRoute{return {id:'r',revision:1,steps:nodes.map(n=>({node_id:n.id,label:n.label,state:'todo',stale:false,available:true})),graph:graph(nodes,edges),target_node_id:nodes[nodes.length-1]?.id,next_node_id:nodes[0]?.id} as SavedLearningRoute}
const props=()=>({projectId:'p',revision:0,onUpdated:vi.fn(),onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn()});
beforeEach(()=>{vi.clearAllMocks();api.graph.mockResolvedValue(graph([node('a'),node('b'),node('free')]))});

test('route projection preserves personal order and real edges without turning order or supplements into prerequisites',()=>{
 const current=route([node('c'),node('a'),node('b'),node('missing')],[edge('supplement','a','c','SUPPLEMENTS'),edge('old','b','c'),edge('outside','a','out')]);
 current.steps[2].stale=true;current.steps[3].available=false;
 current.graph.nodes.push(node('out'));
 const result=selectSavedRouteGraph(current);
 expect(result.nodes.map(n=>n.id)).toEqual(['c','a']);
 expect(result.edges.map(e=>[e.id,e.kind])).toEqual([['supplement','SUPPLEMENTS']]);
 expect(current.graph.edges).toHaveLength(3);
 expect(routeStepLabel({...current.steps[0],state:'done'},'c')).toBe('已完成这一步');
 expect(routeStepLabel(current.steps[2],'b')).toBe('依据变化待复核');
});

test('route graph shows every valid step, its state, original relations and list order',async()=>{
 const nodes=Array.from({length:12},(_,i)=>node(String(i))),current=route(nodes,[edge('real','0','1')]);
 current.steps[0].state='done';current.steps[1].state='skipped';current.steps[3].stale=true;current.next_node_id='2';
 const p=props();render(<KnowledgeGraphView {...p} routeFocused learningRoute={current}/>);
 expect(api.graph).not.toHaveBeenCalled();
 expect(screen.getByLabelText('第1步 · 已完成这一步 · 概念：知识0')).toBeVisible();
 expect(screen.getByLabelText('第3步 · 下一步 · 概念：知识2')).toBeVisible();
 expect(screen.getByLabelText('第12步 · 待继续 · 概念：知识11')).toBeVisible();
 expect(document.querySelectorAll('svg [data-node-id]')).toHaveLength(11);
 expect(document.querySelectorAll('svg [data-edge-id]')).toHaveLength(1);
 fireEvent.click(screen.getByLabelText('关系：关系real'));
 expect(await screen.findByText('检查关系 关系real')).toBeVisible();
 fireEvent.click(within(screen.getByRole('group',{name:'图谱浏览方式'})).getByText('内容列表'));
 const list=screen.getByRole('region',{name:'知识内容列表'});
 expect(within(list).getAllByRole('button').map(button=>button.getAttribute('aria-label'))).toEqual(nodes.filter(n=>n.id!=='3').map(n=>'概念：'+n.label));
 expect(within(list).getByText('第2步 · 已跳过')).toBeVisible();
 fireEvent.click(within(list).getByRole('button',{name:'概念：知识2'}));
 expect(p.onNode).toHaveBeenLastCalledWith(nodes[2]);
 expect(within(screen.getByRole('list',{name:'路线步骤顺序'})).getByText('知识3').closest('button')).toBeDisabled();
});

test('leaving a temporary route restores exploration zoom and viewport without persisting route zoom',async()=>{
 const p=props(),save=vi.fn(),initial:GraphScene={scope:'p/all',search:'',query:'',kind:'',focus:'',zoom:1.15,includeHidden:false,showStructure:false,scrollLeft:175,scrollTop:80};
 const current=route([node('a'),node('b')]);
 const view=render(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save}/>);
 const canvas=screen.getByLabelText('研究知识图谱画布');
 await screen.findByLabelText('概念：知识free');
 expect(canvas.scrollLeft).toBe(175);
 view.rerender(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save} routeFocused learningRoute={current}/>);
 fireEvent.click(screen.getByLabelText('缩小图谱'));
 expect(screen.getByLabelText('重置图谱视角')).toHaveTextContent('100%');
 canvas.scrollLeft=12;canvas.scrollTop=15;fireEvent.scroll(canvas);
 expect(save.mock.lastCall?.[0]).toMatchObject({zoom:1.15,scrollLeft:175,scrollTop:80});
 view.rerender(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save}/>);
 await waitFor(()=>expect(screen.getByLabelText('重置图谱视角')).toHaveTextContent('115%'));
 expect(canvas.scrollLeft).toBe(175);expect(canvas.scrollTop).toBe(80);
 expect(screen.getByLabelText('概念：知识free')).toBeVisible();
});

test('route arrangements use a separate scope and returning restores exploration list mode',async()=>{
 const p=props(),save=vi.fn(),initial:GraphScene={scope:'p/all',search:'',query:'',kind:'',focus:'',zoom:1,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0,displayMode:'list',layouts:{'p/all':{a:{x:40,y:50}}}};
 const current=route([node('a'),node('b')]);
 const view=render(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save}/>);
 await screen.findByRole('region',{name:'知识内容列表'});
 view.rerender(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save} routeFocused learningRoute={current}/>);
 fireEvent.click(screen.getByRole('button',{name:'整理节点'}));
 fireEvent.keyDown(screen.getByLabelText('第1步 · 下一步 · 概念：知识a'),{key:'ArrowRight'});
 await waitFor(()=>expect(save.mock.lastCall?.[0]?.layouts?.['p/route:r']?.a).toBeDefined());
 expect(save.mock.lastCall?.[0]?.layouts?.['p/all']?.a).toEqual({x:40,y:50});
 expect(save.mock.lastCall?.[0]?.displayMode).toBe('list');
 view.rerender(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save}/>);
 await waitFor(()=>expect(screen.getByRole('region',{name:'知识内容列表'})).toBeVisible());
 expect(screen.queryByRole('region',{name:'已保存路线图谱'})).toBeNull();
});

test('a directly mounted route preserves the saved exploration scene before any normal canvas renders',async()=>{
 const p=props(),save=vi.fn(),initial:GraphScene={scope:'p/all',search:'知识',query:'知识',kind:'concept',focus:'a',zoom:1.35,includeHidden:false,showStructure:true,scrollLeft:265,scrollTop:142,displayMode:'list'};
 const current=route([node('a'),node('b')]);
 const view=render(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save} routeFocused learningRoute={current}/>);
 expect(api.graph).not.toHaveBeenCalled();
 fireEvent.click(screen.getByLabelText('缩小图谱'));
 const canvas=screen.getByLabelText('研究知识图谱画布');canvas.scrollLeft=11;fireEvent.scroll(canvas);
 expect(save.mock.lastCall?.[0]).toMatchObject(initial);
 view.rerender(<KnowledgeGraphView {...p} initialScene={initial} onSceneChange={save}/>);
 await waitFor(()=>expect(screen.getByRole('region',{name:'知识内容列表'})).toBeVisible());
 expect(screen.getByLabelText('搜索图谱知识')).toHaveValue('知识');
 fireEvent.click(within(screen.getByRole('group',{name:'图谱浏览方式'})).getByText('结构图'));
 await waitFor(()=>expect(screen.getByLabelText('重置图谱视角')).toHaveTextContent('135%'));
 const restored=screen.getByLabelText('研究知识图谱画布');
 expect(restored.scrollLeft).toBe(265);expect(restored.scrollTop).toBe(142);
});

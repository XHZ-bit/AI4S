import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import type {KnowledgeEdge,KnowledgeGraph,KnowledgeNode} from '../api/knowledge';
const canvas=vi.hoisted(()=>({props:undefined as any,fit:vi.fn(),reheat:vi.fn(),refresh:vi.fn(),center:{x:0,y:0},zoom:1}));
const account=vi.hoisted(()=>({value:{id:'account-a'}}));
const api=vi.hoisted(()=>({graph:vi.fn()}));
vi.mock('react-force-graph-2d',async()=>{const {forwardRef,useImperativeHandle}=await import('react');return {default:forwardRef((props:any,ref)=>{
 canvas.props=props;useImperativeHandle(ref,()=>({zoomToFit:canvas.fit,d3Force:()=>({strength(){},distance(){}}),d3ReheatSimulation:canvas.reheat,refresh:canvas.refresh,
  centerAt:(x?:number,y?:number)=>{if(x!==undefined&&y!==undefined)canvas.center={x,y};return canvas.center},zoom:(value?:number)=>{if(value!==undefined)canvas.zoom=value;return canvas.zoom}}),[]);
 return <div data-testid="force-canvas" data-nodes={props.graphData.nodes.map((node:any)=>node.id).join(',')}/>;
})}});
vi.mock('../components/SessionContext',()=>({useCurrentAccount:()=>account.value}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),getKnowledgeGraph:api.graph}));
vi.mock('../components/knowledge/NodeInspector',()=>({NodeInspector:()=>null,EdgeEditor:({edge}:{edge:KnowledgeEdge})=><p>关系说明 {edge.label}</p>}));
vi.mock('../components/knowledge/KnowledgePathPanel',()=>({default:()=>null}));
import ProjectForceGraph,{networkSceneKey,readNetworkScene} from '../components/knowledge/ProjectForceGraph';
import KnowledgeGraphView from '../components/knowledge/KnowledgeGraph';
import {brightenNodeColor,canvasTooltip,drawForceNode} from '../components/knowledge/forceNodeDrawing';
const node=(id:string,pid='p'):KnowledgeNode=>({id,project_id:pid,source_id:'s',kind:'concept',label:'知识'+id,summary:'解释'+id,parent_id:'root',origin:'user',research_status:'reading',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{semantic:true}});
const edge=(source:string,target:string,pid='p'):KnowledgeEdge=>({id:source+'-'+target,project_id:pid,source_id:'s',source,target,kind:'RELATED_TO',label:'相关',explanation:'用户保存的关联说明',origin:'user',version:1,hidden:false,source_missing:false,evidence_ids:[]});
const graph=(nodes:KnowledgeNode[],edges:KnowledgeEdge[]=[]):KnowledgeGraph=>({nodes,edges,total_nodes:nodes.length,total_edges:edges.length,truncated:false});
const props=()=>({projectId:'p',scope:'p/all',graph:graph([node('a'),node('b')],[edge('a','b')]),onNode:vi.fn(),onEdge:vi.fn(),onClear:vi.fn()});
beforeEach(()=>{localStorage.clear();vi.clearAllMocks();account.value={id:'account-a'};canvas.center={x:0,y:0};canvas.zoom=1;api.graph.mockResolvedValue(graph(Array.from({length:25},(_,i)=>node(String(i)))));});
afterEach(()=>localStorage.clear());

test('tooltip labels retain user text without treating markup as HTML',()=>{
 expect(canvasTooltip('<img src=x onerror="bad"> & \'note\'')).toBe('&lt;img src=x onerror=&quot;bad&quot;&gt; &amp; &#39;note&#39;');
 expect(canvasTooltip('点积 → 注意力')).toBe('点积 → 注意力');
});

test('selected nodes use one brighter filled circle with no ring or halo',()=>{
 const ctx={save:vi.fn(),restore:vi.fn(),beginPath:vi.fn(),arc:vi.fn(),fill:vi.fn(),stroke:vi.fn(),shadowBlur:20,globalAlpha:1,fillStyle:''} as unknown as CanvasRenderingContext2D;
 drawForceNode(ctx,{x:20,y:40},'#438e64',4,true);
 expect(ctx.arc).toHaveBeenCalledExactlyOnceWith(20,40,5.8,0,Math.PI*2);
 expect(ctx.fill).toHaveBeenCalledOnce();expect(ctx.stroke).not.toHaveBeenCalled();
 expect(ctx.shadowBlur).toBe(0);expect(ctx.fillStyle).toBe(brightenNodeColor('#438e64'));
 expect(parseInt(String(ctx.fillStyle).slice(1,3),16)).toBeGreaterThan(0x43);
});

test('selected label space is reserved before ordinary labels without changing graph order or camera',()=>{
 const p=props();render(<ProjectForceGraph {...p} selectedNodeId="b"/>);
 const original=canvas.props.graphData;for(const point of original.nodes)Object.assign(point,{x:100,y:100});
 const ctx={save:vi.fn(),restore:vi.fn(),beginPath:vi.fn(),arc:vi.fn(),fill:vi.fn(),fillText:vi.fn(),measureText:()=>({width:60})} as any;
 canvas.props.onRenderFramePre(ctx,1);
 canvas.props.nodeCanvasObject(original.nodes[0],ctx,1);canvas.props.nodeCanvasObject(original.nodes[1],ctx,1);
 expect(ctx.fillText).toHaveBeenCalledExactlyOnceWith('知识b',100,108);
 expect(canvas.props.graphData).toBe(original);expect(original.nodes.map((point:any)=>point.id)).toEqual(['a','b']);
 expect(canvas.center).toEqual({x:0,y:0});expect(canvas.fit).not.toHaveBeenCalled();
});

test('initial fitting caps a single-node graph at a readable zoom and preserves manual zoom bounds',()=>{
 const p=props();canvas.fit.mockImplementationOnce(()=>{canvas.zoom=40});
 render(<ProjectForceGraph {...p} graph={graph([node('a')])}/>);
 act(()=>canvas.props.onEngineStop());
 expect(canvas.zoom).toBe(2);expect(canvas.props.minZoom).toBe(.1);expect(canvas.props.maxZoom).toBe(12);
 expect(readNetworkScene(networkSceneKey('account-a','p','p/all')).camera?.zoom).toBe(2);
});

test('network input is restricted to its project and selection retains the simulation data and camera',()=>{
 const p=props();p.graph=graph([node('a'),node('b'),node('foreign','other')],[edge('a','b'),edge('a','foreign','other')]);
 const view=render(<ProjectForceGraph {...p}/>);
 expect(screen.getByTestId('force-canvas')).toHaveAttribute('data-nodes','a,b');
 const original=canvas.props.graphData;
 act(()=>canvas.props.onEngineStop());expect(canvas.fit).toHaveBeenCalledOnce();
 fireEvent.change(screen.getByLabelText('定位关系网络节点'),{target:{value:'b'}});
 expect(p.onNode).toHaveBeenCalledWith(p.graph.nodes[1]);
 view.rerender(<ProjectForceGraph {...p} selectedNodeId="b"/>);
 expect(canvas.props.graphData).toBe(original);expect(canvas.fit).toHaveBeenCalledOnce();
 act(()=>canvas.props.onLinkClick(original.links[0]));expect(p.onEdge).toHaveBeenCalledWith(p.graph.edges[0]);
});

test('dragged positions and camera reopen under the same account/project/source scope',()=>{
 const p=props(),key=networkSceneKey('account-a','p','p/all');
 const view=render(<ProjectForceGraph {...p}/>);
 Object.assign(canvas.props.graphData.nodes[0],{x:120,y:-45});canvas.center={x:31,y:22};canvas.zoom=1.7;
 act(()=>canvas.props.onNodeDragEnd(canvas.props.graphData.nodes[0]));
 expect(readNetworkScene(key)).toMatchObject({positions:{a:{x:120,y:-45}},camera:{x:31,y:22,zoom:1.7}});
 view.unmount();render(<ProjectForceGraph {...p}/>);
 expect(canvas.props.graphData.nodes[0]).toMatchObject({x:120,y:-45,fx:120,fy:-45});
 expect(canvas.center).toEqual({x:31,y:22});expect(canvas.zoom).toBe(1.7);
 expect(readNetworkScene(networkSceneKey('other','p','p/all')).positions).toEqual({});
 expect(readNetworkScene(networkSceneKey('account-a','other','other/all')).positions).toEqual({});
 expect(readNetworkScene(networkSceneKey('account-a','p','p/source-two')).positions).toEqual({});
});

test('late cleanup after changing scope cannot write another scope positions into the old profile',()=>{
 const p=props(),oldKey=networkSceneKey('account-a','p','p/all');
 localStorage.setItem(oldKey,JSON.stringify({positions:{a:{x:10,y:20}}}));
 const view=render(<ProjectForceGraph {...p}/>);
 view.rerender(<ProjectForceGraph {...p} scope="p/second" graph={graph([node('second')])}/>);
 expect(readNetworkScene(oldKey).positions).toEqual({a:{x:10,y:20}});
 expect(canvas.props.graphData.nodes[0].id).toBe('second');
 expect(canvas.props.graphData.nodes[0].fx).toBeUndefined();
});

test('editing node text keeps existing points and camera while callbacks receive the current canonical record',()=>{
 const p=props(),view=render(<ProjectForceGraph {...p}/>);
 act(()=>canvas.props.onEngineStop());
 const original=canvas.props.graphData.nodes[0];Object.assign(original,{x:60,y:90});canvas.center={x:22,y:33};canvas.zoom=1.8;
 const revised={...p.graph.nodes[0],label:'修订后的概念',version:2};
 view.rerender(<ProjectForceGraph {...p} graph={graph([revised,p.graph.nodes[1]],p.graph.edges)}/>);
 expect(canvas.props.graphData.nodes[0]).toBe(original);
 expect(canvas.props.graphData.nodes[0]).toMatchObject({fx:60,fy:90,label:revised.label});
 expect(canvas.center).toEqual({x:22,y:33});expect(canvas.zoom).toBe(1.8);expect(canvas.fit).toHaveBeenCalledOnce();
 act(()=>canvas.props.onNodeClick(original));expect(canvas.center).toEqual({x:22,y:33});
 fireEvent.change(screen.getByLabelText('定位关系网络节点'),{target:{value:'a'}});
 expect(p.onNode).toHaveBeenCalledWith(revised);
 expect(canvas.center).toEqual({x:60,y:90});
});

test('a temporary empty or filtered graph retains layouts for the other existing nodes',()=>{
 const key=networkSceneKey('account-a','p','p/all');
 localStorage.setItem(key,JSON.stringify({positions:{a:{x:1,y:2},b:{x:3,y:4}},camera:{x:1,y:1,zoom:1.5}}));
 const p=props(),view=render(<ProjectForceGraph {...p} graph={graph([])}/>);
 view.unmount();expect(readNetworkScene(key).positions).toHaveProperty('b');
 const filtered=render(<ProjectForceGraph {...p} graph={graph([node('a')])}/>);
 act(()=>canvas.props.onEngineStop());filtered.unmount();
 expect(readNetworkScene(key).positions).toMatchObject({a:{x:1,y:2},b:{x:3,y:4}});
});

test('malformed browser layouts do not inject invalid coordinates or camera values',()=>{
 localStorage.setItem('bad',JSON.stringify({positions:{ok:{x:2,y:3},bad:{x:'4',y:2},extreme:{x:1e9,y:0}},camera:{x:0,y:0,zoom:100}}));
 expect(readNetworkScene('bad')).toEqual({positions:{ok:{x:2,y:3}}});
});

test('project graph toggles persist the selected presentation and keep other projects independent',async()=>{
 const p={projectId:'p',revision:0,onUpdated:vi.fn(),onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),onCreateNode:vi.fn(),onImport:vi.fn()};
 const view=render(<KnowledgeGraphView {...p}/>);
 await screen.findByLabelText('概念：知识0');
 fireEvent.click(screen.getByRole('button',{name:'新增节点'}));expect(p.onCreateNode).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole('button',{name:'导入资料'}));expect(p.onImport).toHaveBeenCalledOnce();
 fireEvent.click(within(screen.getByRole('group',{name:'图谱浏览方式'})).getByText('关系网络'));
 await screen.findByRole('region',{name:'课题关系网络'});
 expect(canvas.props.graphData.nodes).toHaveLength(25);
 expect(localStorage.getItem('paperstride:account-a:graph-presentation:p')).toBe('network');
 expect(api.graph).toHaveBeenCalledWith('p',expect.any(Object),expect.any(AbortSignal));
 view.unmount();
 const other=render(<KnowledgeGraphView {...p} projectId="other"/>);
 await waitFor(()=>expect(api.graph).toHaveBeenCalledWith('other',expect.any(Object),expect.any(AbortSignal)));
 expect(screen.queryByRole('region',{name:'课题关系网络'})).toBeNull();
 other.unmount();render(<KnowledgeGraphView {...p}/>);
 await screen.findByRole('region',{name:'课题关系网络'});
});

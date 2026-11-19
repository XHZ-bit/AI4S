import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeWorkbench from '../components/knowledge/KnowledgeWorkbench';
import type {KnowledgeEvidence,KnowledgeNode} from '../api/knowledge';
import {project} from './research/fixtures';

const api=vi.hoisted(()=>({sources:vi.fn(),graph:vi.fn(),node:vi.fn(),route:vi.fn()}));
vi.mock('../api/projects',()=>({getProject:vi.fn(async()=>project)}));
vi.mock('../api/client',()=>({apiGet:vi.fn(async()=>({})),apiPost:vi.fn(),apiPatch:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),listKnowledgeSources:api.sources,getKnowledgeGraph:api.graph,getKnowledgeNode:api.node}));
vi.mock('../api/knowledgeRoutes',async()=>({...await vi.importActual<typeof import('../api/knowledgeRoutes')>('../api/knowledgeRoutes'),getLearningRoute:api.route}));
vi.mock('../components/knowledge/NodeInspector',()=>({NodeInspector:({onEvidence,onClose}:{onEvidence:(e:KnowledgeEvidence)=>void;onClose:()=>void})=><aside aria-label="测试节点侧栏"><button onClick={()=>onEvidence({id:'e',source_id:'s1',source_title:'资料A',block_id:'b',quote:'原文片段',locator:{page:2},source_version:'v1',origin:'source'})}>查看原文依据</button><button onClick={onClose}>关闭节点</button></aside>,EdgeEditor:()=>null}));
vi.mock('../components/knowledge/KnowledgePathPanel',()=>({default:()=>null}));
vi.mock('../components/knowledge/LearningRoute',()=>({default:({onGraph}:{onGraph:()=>void})=><section aria-label="测试路线编辑"><button onClick={onGraph}>在图谱中查看路线</button></section>}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({default:()=>null,AnalysisStatus:()=>null,SourceReader:()=> <section aria-label="测试原文阅读"/>}));
vi.mock('../components/knowledge/TaskGuidance',()=>({default:()=>null}));
vi.mock('../components/knowledge/LearningRouteContinue',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgeLearning',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgeComparison',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgePractice',()=>({default:()=>null}));
const node=(id:string):KnowledgeNode=>({id,project_id:'project-1',source_id:'s1',kind:'concept',label:'知识'+id,summary:'说明',parent_id:'root',origin:'source',research_status:'reading',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{semantic:true}});
const free=node('free'),goal=node('goal');
function Location(){return <output data-testid="location">{useLocation().search}</output>}
function button(name:string){
 const target=screen.getByText(name,{selector:'button,button>span'}).closest('button');
 if(!target)throw new Error('Missing button: '+name);
 return target;
}
beforeEach(()=>{
 localStorage.clear();vi.clearAllMocks();
 api.sources.mockResolvedValue({items:[{id:'s1',title:'资料A',version:'v1',kind:'paper',removed:false}],preferences:{mode:'research',view:null},model:{configured:false,enabled:false}});
 api.graph.mockResolvedValue({nodes:[free,goal],edges:[],total_nodes:2,total_edges:0,truncated:false});
 api.node.mockImplementation(async(_p:string,id:string)=>({node:id==='free'?free:goal,evidence:[],neighbors:[],edges:[],prerequisites:[],resources:[]}));
 api.route.mockResolvedValue({route:{id:'r',revision:1,steps:[{node_id:'goal',label:goal.label,state:'todo',stale:false,available:true}],graph:{nodes:[goal],edges:[]},target_node_id:'goal',next_node_id:'goal'}});
});

// Multi-view Ant Design rendering is slow in JSDOM; actual canvas timing is
// verified separately in the desktop browser regression.
test('a route and original-text roundtrip restores the original scoped canvas instead of resetting its focus and zoom',async()=>{
 render(<MemoryRouter initialEntries={['/research/project-1?view=graph&source=s1&node=free']}><Routes><Route path="/research/:projectId" element={<><KnowledgeWorkbench projectId="project-1"/><Location/></>}/></Routes></MemoryRouter>);
 await screen.findByLabelText('概念：知识free',{}, {timeout:5000});
 fireEvent.click(screen.getByLabelText('放大图谱'));fireEvent.click(screen.getByLabelText('放大图谱'));fireEvent.click(screen.getByLabelText('放大图谱'));
 const canvas=screen.getByLabelText('研究知识图谱画布');canvas.scrollLeft=130;canvas.scrollTop=75;fireEvent.scroll(canvas);
 const key='paperstride:knowledge-scene:project-1:canvas';
 const before=JSON.parse(localStorage.getItem(key)!);
 expect(before).toMatchObject({scope:'project-1/s1',focus:'free',scrollLeft:130,scrollTop:75});
 fireEvent.click(button('学习路线'));
 fireEvent.click(await screen.findByText('在图谱中查看路线',{selector:'button'}));
 await screen.findByRole('region',{name:'已保存路线图谱'});
 fireEvent.click(screen.getByLabelText('放大图谱'));
 fireEvent.click(screen.getByLabelText('第1步 · 下一步 · 概念：知识goal'));
 fireEvent.click(button('查看原文依据'));
 await screen.findByRole('region',{name:'测试原文阅读'});
 fireEvent.click(screen.getByRole('button',{name:'返回原位置'}));
 await screen.findByRole('region',{name:'已保存路线图谱'});
 fireEvent.click(button('返回自由探索图谱'));
 await screen.findByLabelText('概念：知识free');
 await waitFor(()=>expect(screen.getByTestId('location')).toHaveTextContent('source=s1'));
 expect(screen.getByTestId('location')).toHaveTextContent('node=free');
 expect(JSON.parse(localStorage.getItem(key)!)).toMatchObject({scope:before.scope,focus:before.focus,zoom:before.zoom});
 const restored=screen.getByLabelText('研究知识图谱画布');expect(restored.scrollLeft).toBe(130);expect(restored.scrollTop).toBe(75);
},30000);

import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeWorkbench from '../components/knowledge/KnowledgeWorkbench';
import {project} from './research/fixtures';

const api=vi.hoisted(()=>({project:vi.fn(),update:vi.fn()}));
vi.mock('../api/projects',()=>({getProject:api.project,updateProject:api.update}));
vi.mock('../api/client',()=>({apiGet:vi.fn(async()=>({})),apiPost:vi.fn(),apiPatch:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),listKnowledgeSources:vi.fn(async()=>({items:[],preferences:{mode:'research'},model:{configured:true,enabled:true}}))}));
vi.mock('../api/knowledgeRoutes',async()=>({...await vi.importActual<typeof import('../api/knowledgeRoutes')>('../api/knowledgeRoutes'),getLearningRoute:vi.fn(async()=>({route:null}))}));
vi.mock('../components/knowledge/KnowledgeGraph',()=>({default:({questionFocused}:{questionFocused:boolean})=><section aria-label="测试课题图谱">{questionFocused?'问题视图':'完整视图'}</section>}));
vi.mock('../components/knowledge/TaskGuidance',()=>({default:()=> <aside aria-label="下一步指导">下一步</aside>}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({default:()=>null,AnalysisStatus:()=>null,SourceReader:()=>null}));
vi.mock('../components/knowledge/LearningRoute',()=>({default:()=>null}));
vi.mock('../components/knowledge/LearningRouteContinue',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgeLearning',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgeComparison',()=>({default:()=>null}));
vi.mock('../components/knowledge/KnowledgePractice',()=>({default:()=>null}));

beforeEach(()=>{localStorage.clear();vi.clearAllMocks();api.project.mockResolvedValue(project)});
function show(){render(<MemoryRouter initialEntries={['/research/project-1']}><KnowledgeWorkbench projectId="project-1"/></MemoryRouter>)}

test('an empty question keeps its direct entry and first guidance without a placeholder heading',async()=>{
 api.project.mockResolvedValue({...project,research_question:''});show();
 const bar=within(await screen.findByRole('region',{name:'当前研究问题'}));
 expect(bar.getByRole('button',{name:'写下问题'})).toBeVisible();
 expect(bar.queryByRole('heading')).toBeNull();
 expect(screen.queryByText('这次想弄懂什么？')).toBeNull();
 expect(screen.getByRole('complementary',{name:'下一步指导'})).toBeVisible();
 fireEvent.click(bar.getByRole('button',{name:'切换完整图谱'}));
 expect(screen.getByRole('region',{name:'测试课题图谱'})).toHaveTextContent('完整视图');
 expect(bar.getByRole('button',{name:'围绕当前问题'})).toBeVisible();
});

test('a long question can be expanded while retaining the original wording and edit action',async()=>{
 const question='如何把论文中的注意力公式对应到实际实现，并逐项检查输入维度、缩放项、掩码与归一化的先后次序？'.repeat(3);
 api.project.mockResolvedValue({...project,research_question:question});show();
 const bar=within(await screen.findByRole('region',{name:'当前研究问题'}));
 const expand=bar.getByRole('button',{name:'展开问题'});
 expect(expand).toHaveAttribute('aria-expanded','false');
 expect(bar.getByRole('heading',{name:question})).toHaveAttribute('title',question);
 fireEvent.click(expand);
 expect(bar.getByRole('button',{name:'收起问题'})).toHaveAttribute('aria-expanded','true');
 fireEvent.click(bar.getByRole('button',{name:'修改问题'}));
 expect(bar.getByRole('textbox',{name:'当前研究问题'})).toHaveValue(question);
});

test('switching graph scope and a failed save preserve an unfinished question',async()=>{
 api.update.mockRejectedValueOnce(new Error('服务暂不可用'));show();
 const bar=within(await screen.findByRole('region',{name:'当前研究问题'}));
 fireEvent.click(bar.getByRole('button',{name:'修改问题'}));
 const editor=bar.getByRole('textbox',{name:'当前研究问题'});
 fireEvent.change(editor,{target:{value:'我还在修改的研究问题'}});
 fireEvent.click(bar.getByRole('button',{name:'切换完整图谱'}));
 expect(editor).toHaveValue('我还在修改的研究问题');
 fireEvent.click(bar.getByRole('button',{name:'保存问题'}));
 await bar.findByText('问题尚未保存，输入已保留');
 expect(editor).toHaveValue('我还在修改的研究问题');
 api.update.mockResolvedValueOnce({...project,version:4,research_question:'我还在修改的研究问题'});
 fireEvent.click(bar.getByRole('button',{name:'保存问题'}));
 await waitFor(()=>expect(bar.queryByRole('textbox',{name:'当前研究问题'})).toBeNull());
 expect(bar.getByRole('heading',{name:'我还在修改的研究问题'})).toBeVisible();
});

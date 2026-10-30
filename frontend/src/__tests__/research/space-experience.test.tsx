import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import {LegacyResearchProjectPage as ResearchProjectPage} from '../../pages/research/ResearchProjectPage';
import {project} from './fixtures';
const api=vi.hoisted(()=>({getProject:vi.fn(),apiGet:vi.fn()}));
vi.mock('../../api/projects',()=>({getProject:api.getProject}));
vi.mock('../../api/client',()=>({apiGet:api.apiGet,apiPost:vi.fn()}));
vi.mock('../../components/workbench/SceneSync',()=>({default:()=>null}));
vi.mock('../../components/workbench/ProjectOverview',()=>({default:()=> <div>overview-content</div>}));
vi.mock('../../components/workbench/ProjectReading',()=>({default:()=> <div>reader-content</div>}));
vi.mock('../../components/workbench/ProjectWorkbench',()=>({default:()=> <div>records-editor</div>}));
vi.mock('../../components/workbench/EvidenceMatrix',()=>({default:()=> <div>evidence-matrix</div>}));
vi.mock('../../components/workbench/DiffusionPractice',()=>({default:()=> <div>diffusion-practice</div>}));
vi.mock('../../components/workbench/ResearchPlan',()=>({default:()=> <div>research-plan</div>}));
vi.mock('../../components/research/ComparisonPanel',()=>({default:()=> <div>strict-comparison</div>}));
vi.mock('../../components/research/EvidencePanel',()=>({default:()=> <div>facts-panel</div>}));
vi.mock('../../components/research/PlansPanel',()=>({default:()=> <div>formal-plan</div>}));
vi.mock('../../components/research/ProjectSettingsPanel',()=>({default:()=> <div>project-settings</div>}));
vi.mock('../../components/workspace/ResearchCanvas',()=>({default:()=>null}));
vi.mock('../../components/research/DecisionOverview',()=>({default:()=>null}));
vi.mock('../../components/workspace/ScenarioPanel',()=>({default:()=> <div>resource-scenario</div>}));
vi.mock('../../components/workspace/DiffPanel',()=>({default:()=>null}));
vi.mock('../../components/research/ProjectAuditPanel',()=>({default:()=>null}));
vi.mock('../../components/research/LocalRadarPanel',()=>({default:()=>null}));
function show(query:string){render(<MemoryRouter initialEntries={['/research/project-1?'+query]}><Routes><Route path="/research/:projectId" element={<ResearchProjectPage/>}/></Routes></MemoryRouter>)}
beforeEach(()=>{api.getProject.mockReset().mockResolvedValue(project);api.apiGet.mockReset().mockResolvedValue({project,papers:[],records:[],sessions:[],features:{foundations:true,quizzes:true,coding:true,visuals:true,paper_guidance:true,graph:true}})});
test('legacy record links open the canonical outcomes editor without mounting every output tool',async()=>{
 show('tab=workbench&record=note-1');expect(await screen.findByText('records-editor')).toBeTruthy();expect(screen.queryByText('research-plan')).toBeNull();expect(screen.queryByText('formal-plan')).toBeNull();expect(screen.queryByText('overview-content')).toBeNull();
});
test('legacy resource scenario links retain their exact destination',async()=>{show('tab=scenarios');expect(await screen.findByText('resource-scenario')).toBeTruthy();expect(screen.queryByText('evidence-matrix')).toBeNull();expect(screen.queryByText('strict-comparison')).toBeNull()});
test('nonrobotics research never mounts the diffusion practice',async()=>{show('tab=practice');expect(await screen.findByText('围绕当前问题补充知识')).toBeTruthy();expect(screen.queryByText('diffusion-practice')).toBeNull();expect(screen.getByRole('link',{name:'带着问题开始学习'}).getAttribute('href')).toContain('project=project-1')});
test('practice stays absent until project preferences arrive and remains hidden when disabled',async()=>{
 let resolve!:(value:any)=>void;api.apiGet.mockReturnValueOnce(new Promise(done=>{resolve=done}));show('tab=overview');await screen.findByText('overview-content');expect(screen.queryByRole('tab',{name:'实践'})).toBeNull();
 resolve({project,papers:[],features:{foundations:false,quizzes:false,coding:false,visuals:false,paper_guidance:false}});await waitFor(()=>expect(screen.queryByRole('tab',{name:'实践'})).toBeNull());
});
test('changing outcomes tool loads just the selected workflow',async()=>{show('tab=outcomes');await screen.findByText('records-editor');fireEvent.mouseDown(screen.getByRole('combobox',{name:'成果内容'}));fireEvent.click(await screen.findByText('研究计划'));expect(await screen.findByText('research-plan')).toBeTruthy();expect(screen.queryByText('records-editor')).toBeNull();expect(screen.queryByText('formal-plan')).toBeNull()});

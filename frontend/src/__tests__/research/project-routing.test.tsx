import {render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation,useSearchParams} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import ResearchProjectPage from '../../pages/research/ResearchProjectPage';
import {project} from './fixtures';

const api=vi.hoisted(()=>({getProject:vi.fn(),apiGet:vi.fn()}));
vi.mock('../../api/projects',()=>({getProject:api.getProject}));
vi.mock('../../api/client',()=>({apiGet:api.apiGet,apiPost:vi.fn()}));
vi.mock('../../components/knowledge/KnowledgeWorkbench',()=>({default:({projectId}:{projectId:string})=>{const [p]=useSearchParams();return <div data-testid="knowledge-workbench">{projectId}:{p.get('view')||'graph'}</div>}}));
vi.mock('../../components/workbench/SceneSync',()=>({default:()=>null}));
vi.mock('../../components/research/ProjectSettingsPanel',()=>({default:()=> <div>formal-settings</div>}));
vi.mock('../../components/research/PlansPanel',()=>({default:()=> <div>formal-plans</div>}));
function Location(){return <output data-testid="route-location">{useLocation().search}</output>}
function show(query=''){return render(<MemoryRouter initialEntries={['/research/project-1'+query]}><Routes><Route path="/research/:projectId" element={<><ResearchProjectPage/><Location/></>}/></Routes></MemoryRouter>)}
beforeEach(()=>{api.getProject.mockReset().mockResolvedValue(project);api.apiGet.mockReset().mockResolvedValue({project,papers:[],records:[],features:{}})});

test.each([['','graph'],['?tab=overview','graph'],['?tab=reading&paper=p1&page=14','reading'],['?tab=compare&comparison=conditions','compare'],['?tab=practice&node=n1','practice']])('default/old route %s uses the knowledge workbench and never mounts the old page',async(query,view)=>{
 show(query);
 await waitFor(()=>expect(screen.getByTestId('knowledge-workbench').textContent).toBe('project-1:'+view));
 expect(api.getProject).not.toHaveBeenCalled();expect(api.apiGet).not.toHaveBeenCalled();
 if(query.includes('paper=')){expect(screen.getByTestId('route-location').textContent).toContain('paper=p1');expect(screen.getByTestId('route-location').textContent).toContain('page=14')}
 if(query.includes('conditions'))expect(screen.getByTestId('route-location').textContent).not.toContain('comparison=conditions');
});

test.each([['settings','formal-settings'],['plans','formal-plans']])('explicit advanced legacy %s remains reachable',async(tab,content)=>{
 show('?legacy=1&tab='+tab);
 await screen.findByText(content);
 expect(screen.queryByTestId('knowledge-workbench')).toBeNull();
 expect(api.getProject).toHaveBeenCalled();
});

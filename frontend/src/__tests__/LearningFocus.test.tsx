import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {beforeEach,vi} from 'vitest';
import Learn from '../pages/Learn';
import DiffusionPractice from '../components/workbench/DiffusionPractice';
import {apiGet} from '../api/client';
vi.mock('../api/client',()=>({apiGet:vi.fn(),apiPost:vi.fn()}));
vi.mock('../components/learning/TutorChat',()=>({default:()=> <div>tutor content</div>}));
vi.mock('../components/learning/CodePractice',()=>({default:({projectId}:any)=> <div>code practice for {projectId||'standalone'}</div>}));
vi.mock('../components/learning/Quiz',()=>({default:({projectId}:any)=> <div>quiz for {projectId}</div>}));
vi.mock('../components/learning/ConceptVisual',()=>({default:()=> <div>interactive visual</div>}));
vi.mock('../components/workbench/SyncedDraft',()=>({default:()=>null}));
const lesson={id:'dp-1',title:'Conditional probability',summary:'Learn distributions',minutes:10,connection:'Connect to paper',prerequisites:[],steps:[{question:'First question?',explanation:'First explanation'},{question:'Second question?',explanation:'Second explanation'}],terms:[],quiz:[{question:'Check?',options:['a','b']}],exercise:{id:'e'},visual:'distribution',sources:[{url:'https://example.org/paper',title:'Paper'}]};
const features={foundations:true,glossary:true,quizzes:true,coding:true,visuals:true,paper_guidance:true};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(apiGet).mockImplementation(async(path)=>path.includes('/curriculum')?{items:[lesson],features,checks:[],version:'v1'}:path.includes('/projects/')?{features}:{items:[lesson],attempts:[]});});
test('standalone course library still shows one activity and preserves paper context',async()=>{
 render(<MemoryRouter initialEntries={['/learn?view=foundations&paper=paper1&page=5&returnTo=%2Fpapers%2Fpaper1%3Ftab%3Dreading%26page%3D5']}><Learn/></MemoryRouter>);
 expect(await screen.findByText('First explanation')).toBeTruthy();expect(screen.queryByText('Second explanation')).toBeNull();expect(screen.queryByText('quiz for undefined')).toBeNull();expect(screen.queryByText('code practice for standalone')).toBeNull();
 const href=screen.getByRole('link',{name:'这里没懂，换一种讲法'}).getAttribute('href')!;expect(href).toContain('paper=paper1');expect(href).toContain('page=5');expect(href).toContain('returnTo=');
 fireEvent.click(screen.getByRole('button',{name:'下一个问题'}));expect(screen.getByText('Second explanation')).toBeTruthy();expect(screen.queryByText('First explanation')).toBeNull();
 fireEvent.click(screen.getByText('代码实践'));expect(screen.getByText('code practice for standalone')).toBeTruthy();expect(screen.queryByText('Second explanation')).toBeNull();
 expect(screen.getByRole('link',{name:'返回刚才的阅读'}).getAttribute('href')).toBe('/papers/paper1?tab=reading&page=5');
});
test('disabled project learning prevents lesson requests',async()=>{
 vi.mocked(apiGet).mockResolvedValue({features:Object.fromEntries(Object.keys(features).map(k=>[k,false]))});
 render(<MemoryRouter initialEntries={['/learn?view=tutor&project=closed']}><Learn/></MemoryRouter>);
 expect(await screen.findByText('学习功能已关闭')).toBeTruthy();expect(vi.mocked(apiGet).mock.calls.every(([path])=>path!='/api/tutor/lessons')).toBe(true);
});

function PracticeDestination(){const location=useLocation();return <output data-testid="practice-destination">{location.pathname+location.search}</output>}
test.each(['foundations','coding'])('project %s links open node practice without loading the fixed course library',async view=>{
 const original='/research/p?view=reading&node=gate-node&source=report-source&paper=paper1&page=5';
 render(<MemoryRouter initialEntries={['/learn?project=p&view='+view+'&returnTo='+encodeURIComponent(original)]}><Routes><Route path="/learn" element={<Learn/>}/><Route path="/research/:projectId" element={<PracticeDestination/>}/></Routes></MemoryRouter>);
 const destination=await screen.findByTestId('practice-destination');const url=new URL(destination.textContent!,'http://paperstride.local');expect(url.pathname).toBe('/research/p');expect(url.searchParams.get('view')).toBe('practice');expect(url.searchParams.get('node')).toBe('gate-node');expect(url.searchParams.get('source')).toBe('report-source');expect(url.searchParams.get('paper')).toBe('paper1');expect(url.searchParams.get('returnTo')).toBe(original);expect(apiGet).not.toHaveBeenCalled();
});
test('diffusion practice reveals only current step and requested activity',async()=>{
 render(<MemoryRouter initialEntries={['/practice?project=p']}><DiffusionPractice/></MemoryRouter>);
 expect(await screen.findByText('First explanation')).toBeTruthy();expect(screen.queryByText('Second explanation')).toBeNull();expect(screen.queryByText('code practice for p')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'下一个问题'}));expect(screen.getByText('Second explanation')).toBeTruthy();
 fireEvent.click(screen.getByText('代码实践'));expect(screen.getByText('code practice for p')).toBeTruthy();expect(screen.queryByText('Second explanation')).toBeNull();
 fireEvent.click(screen.getByText('记录与回顾'));expect(screen.getByRole('textbox',{name:'课题实验解释'})).toBeTruthy();expect(screen.queryByText('code practice for p')).toBeNull();
});

test('disabled tutoring deep link falls back to enabled courses',async()=>{
 vi.mocked(apiGet).mockImplementation(async(path)=>path.includes('/projects/')?{features:{...features,paper_guidance:false}}:{items:[lesson],attempts:[]});
 render(<MemoryRouter initialEntries={['/learn?view=tutor&project=p']}><Learn/></MemoryRouter>);
 expect(await screen.findByText('First explanation')).toBeTruthy();expect(screen.queryByText('tutor content')).toBeNull();
 expect(vi.mocked(apiGet).mock.calls.some(([path])=>path==='/api/tutor/lessons')).toBe(true);
});

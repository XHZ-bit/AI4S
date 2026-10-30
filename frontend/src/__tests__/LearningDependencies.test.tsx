import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import LearningDependencies,{dependencyLayout} from '../components/workbench/LearningDependencies';
import {apiGet,apiPost} from '../api/client';

vi.mock('../api/client',()=>({apiGet:vi.fn(),apiPost:vi.fn()}));
const nodes=[{id:'vectors',title:'向量与矩阵'},{id:'probability',title:'概率分布'},{id:'dp-1',title:'条件动作分布'},{id:'dp-3',title:'前向加噪'}];
const edges=[{source:'probability',target:'dp-1',origin:'teaching_suggestion'},{source:'dp-1',target:'dp-3',origin:'teaching_suggestion'},{source:'vectors',target:'dp-3',origin:'user_input'}];
const graph={version:3,nodes,data:edges};
const curriculum={features:{foundations:true,coding:true,quizzes:true},checks:[{id:'dp-1',state:'本轮通过',checked:2,code_checked:true},{id:'dp-3',state:'需要复习',checked:1,code_checked:false}]};
const show=(projectId?:string)=>render(<MemoryRouter initialEntries={['/explore?mode=learning']}><LearningDependencies projectId={projectId}/></MemoryRouter>);

beforeEach(()=>{
  vi.resetAllMocks();
  vi.mocked(apiGet).mockImplementation(async(path)=>path.includes('/history')?{items:[]} as never:path.includes('/curriculum')?curriculum as never:graph as never);
  vi.mocked(apiPost).mockImplementation(async(_path,body:any)=>({version:4,data:body.edges}) as never);
});

test('shows a readable branching graph, source kinds and project-scoped learning actions',async()=>{
  show('project-one');
  fireEvent.click(await screen.findByRole('button',{name:'选择知识点：前向加噪'}));
  const details=screen.getByRole('complementary',{name:'知识点详情'});
  expect(within(details).getByText('学习检查：需要复习')).toBeTruthy();
  expect(within(details).getByRole('button',{name:'条件动作分布'})).toBeTruthy();
  expect(within(details).getByRole('button',{name:'向量与矩阵'})).toBeTruthy();
  expect(within(details).getByText('教学建议')).toBeTruthy();
  expect(within(details).getByText('个人调整')).toBeTruthy();
  const learningUrl=new URL(within(details).getByRole('link',{name:'打开这节学习内容'}).getAttribute('href')!, 'http://localhost');
  expect(learningUrl.pathname).toBe('/practice');
  expect(Object.fromEntries(learningUrl.searchParams)).toEqual({unit:'dp-3',project:'project-one',returnTo:'/explore?mode=learning'});
  expect(apiGet).toHaveBeenCalledWith('/api/stride/curriculum',{project_id:'project-one'},expect.any(AbortSignal));
  const surface=screen.getByRole('group',{name:'学习依赖图，可滚动查看完整关系'});
  expect(within(surface).getAllByRole('button')).toHaveLength(4);
  expect(surface.querySelectorAll('path.dependency-edge')).toHaveLength(3);
});

test('keyboard follows dependency direction and focused nodes update their details',async()=>{
  show();const start=await screen.findByRole('button',{name:'选择知识点：概率分布'});
  start.focus();fireEvent.keyDown(start,{key:'ArrowDown'});
  expect(document.activeElement).toBe(screen.getByRole('button',{name:'选择知识点：条件动作分布'}));
  expect(within(screen.getByRole('complementary',{name:'知识点详情'})).getByText('学习检查：本轮通过')).toBeTruthy();
});

test('removing one dependency keeps others and submits the current version',async()=>{
  show('project-one');fireEvent.click(await screen.findByRole('button',{name:'选择知识点：前向加噪'}));
  fireEvent.click(screen.getByRole('button',{name:'移除依赖：向量与矩阵先于前向加噪'}));
  expect(await screen.findByText('学习顺序已保存')).toBeTruthy();
  expect(apiPost).toHaveBeenCalledWith('/api/stride/dependencies?project_id=project-one',{version:3,edges:edges.slice(0,2)});
  expect(screen.getByRole('group',{name:'学习依赖图，可滚动查看完整关系'}).querySelectorAll('path.dependency-edge')).toHaveLength(2);
});

test('conflicts preserve the displayed graph and offer a refresh rather than overwriting',async()=>{
  vi.mocked(apiPost).mockRejectedValue(Object.assign(new Error('conflict'),{status:409}));
  show();fireEvent.click(await screen.findByRole('button',{name:'选择知识点：前向加噪'}));
  fireEvent.click(screen.getByRole('button',{name:'移除依赖：向量与矩阵先于前向加噪'}));
  expect(await screen.findByText(/另一处已修改学习顺序/)).toBeTruthy();
  expect(screen.getByRole('group',{name:'学习依赖图，可滚动查看完整关系'}).querySelectorAll('path.dependency-edge')).toHaveLength(3);
  expect(screen.getByRole('button',{name:'重新加载学习顺序'})).toBeTruthy();
});

test('changing projects rejects a late response from the earlier scope',async()=>{
  let finish!:(value:any)=>void;const delayed=new Promise(resolve=>{finish=resolve});
  vi.mocked(apiGet).mockImplementation(async(path)=>path.includes('/curriculum')?curriculum as never:path.includes('project-old')?await delayed as never:{...graph,nodes:[{id:'new',title:'新课题知识点'}],data:[]} as never);
  const view=show('project-old');
  view.rerender(<MemoryRouter><LearningDependencies projectId="project-new"/></MemoryRouter>);
  expect(await screen.findByRole('button',{name:'选择知识点：新课题知识点'})).toBeTruthy();
  await act(async()=>finish(graph));
  expect(screen.queryByRole('button',{name:'选择知识点：前向加噪'})).toBeNull();
  expect(screen.getByRole('button',{name:'选择知识点：新课题知识点'})).toBeTruthy();
});

test('the layout respects long prerequisite paths and detects saved cycles',()=>{
  const layout=dependencyLayout(nodes,edges);const at=(id:string)=>layout.positions.find(node=>node.id===id)!;
  expect(at('dp-3').y).toBeGreaterThan(at('dp-1').y);expect(at('dp-1').y).toBeGreaterThan(at('probability').y);
  expect(layout.hasCycle).toBe(false);
  expect(dependencyLayout(nodes,[...edges,{source:'dp-3',target:'probability',origin:'user_input'}]).hasCycle).toBe(true);
});

test('small screens start with complete readable stages and can follow the next knowledge',async()=>{
  const original=window.innerWidth;Object.defineProperty(window,'innerWidth',{value:390,configurable:true});
  try{
    show();await screen.findByRole('button',{name:'选择知识点：概率分布'});
    expect(screen.getByText('从这些基础开始')).toBeTruthy();
    expect(screen.queryByRole('group',{name:'学习依赖图，可滚动查看完整关系'})).toBeNull();
    fireEvent.click(within(screen.getByRole('group',{name:'后续学习入口'})).getByRole('button',{name:'条件动作分布'}));
    expect(screen.getByRole('button',{name:'选择知识点：条件动作分布'})).toBeTruthy();
    expect(within(screen.getByRole('complementary',{name:'知识点详情'})).getByText('学习检查：本轮通过')).toBeTruthy();
  }finally{Object.defineProperty(window,'innerWidth',{value:original,configurable:true});}
});

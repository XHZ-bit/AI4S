import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import type {KnowledgePracticeArtifact} from '../api/knowledgePractice';
import KnowledgePractice from '../components/knowledge/KnowledgePractice';

const api=vi.hoisted(()=>({get:vi.fn(),generate:vi.fn(),version:vi.fn(),save:vi.fn(),record:vi.fn(),run:vi.fn(),cancel:vi.fn()}));
vi.mock('../api/knowledgePractice',()=>({getNodePractice:api.get,generateNodePractice:api.generate,getPracticeVersion:api.version,savePracticeDraft:api.save,recordPracticeRun:api.record}));
vi.mock('../components/knowledge/practiceRuntime',()=>({runBrowserPython:api.run}));
vi.mock('../components/knowledge/KnowledgeText',()=>({default:({text}:{text:string})=><p>{text}</p>}));
vi.mock('antd',()=>{
 const Input=Object.assign((p:Record<string,unknown>)=><input {...p}/>,{TextArea:({autoSize:_,...p}:Record<string,unknown>)=><textarea {...p}/>});
 return {Input,Button:({children,loading:_,type:__,danger:___,...p}:Record<string,unknown>)=><button {...p}>{children as React.ReactNode}</button>,
  Select:({options,onChange,...p}:{options:{value:string;label:string}[];onChange:(value:string)=>void})=><select {...p} onChange={e=>onChange(e.target.value)}>{options.map(o=><option value={o.value} key={o.value}>{o.label}</option>)}</select>,
  Space:({children}:{children:React.ReactNode})=><div>{children}</div>,Tag:({children}:{children:React.ReactNode})=><span>{children}</span>,Spin:()=>null,
  Alert:({message,description,action}:{message:string;description?:string;action?:React.ReactNode})=><div role="alert">{message}{description}{action}</div>};
});
function artifact(id='p1'):KnowledgePracticeArtifact{return {id,project_id:'space1',node_id:'n1',node_label:'Synthetic scale',node_version:1,source_version:'sha256:fixture',goal:'Understand scale',difficulty:'foundation',title:'Scale starter',prompt:'Implement the fixture scale.',status:'starter',origin:'teaching_starter',revision:1,created_at:'2026-10-29T12:00:00Z',starter_code:'print(inputs["x"])',draft_code:'print(inputs["x"])',test_code:'assert inputs["x"] == 2',reference_code:'',input_json:'{"x":2}',hints:['Print x first.'],expected_behavior:'A teaching observation.',learning_objectives:['Understand scale'],simplifications:['Synthetic source, not a research result.'],evidence:[],errors:[],usage:{},cached:false,stale:false,versions:[{id,title:'Scale starter',goal:'Understand scale',difficulty:'foundation',status:'starter',node_version:1,revision:1,created_at:'2026-10-29T12:00:00Z'}],runs:[]}}
beforeEach(()=>{vi.clearAllMocks();localStorage.clear();api.get.mockResolvedValue(artifact());api.generate.mockResolvedValue({...artifact('p2'),status:'ready',title:'Adjusted task'});api.save.mockImplementation((_p,_id,body)=>Promise.resolve({...artifact(),draft_code:body.code,input_json:body.input_json,revision:2}));api.record.mockImplementation((_p,id,body)=>Promise.resolve({...body,id:'r1',practice_id:id,created_at:'now',origin:'browser_teaching_run'}));api.run.mockImplementation((_code,_inputs,_tests,callbacks)=>{callbacks.onState('running');return {cancel:api.cancel}})});

test('no node only guides selection and never requests a course',()=>{
 render(<KnowledgePractice projectId="space1" onBack={vi.fn()}/>);
 expect(screen.getByRole('heading',{name:'选择一个知识节点开始练习'})).toBeVisible();expect(api.get).not.toHaveBeenCalled();expect(api.generate).not.toHaveBeenCalled();
});
test('empty output and unsupported content do not occupy the practice page before a run',async()=>{
 api.get.mockResolvedValue({...artifact(),hints:[],test_code:'',reference_code:'',evidence:[],expected_behavior:''});
 const {container}=render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 expect(container.querySelector('.kw-practice-result')).toBeNull();
 expect(container.querySelector('.kw-practice-support')).toBeNull();
 expect(screen.queryByText('预期观察：')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 expect(await screen.findByRole('heading',{name:'正在运行'})).toBeVisible();
 expect(container.querySelector('.kw-practice-result')).not.toBeNull();
});
test('loading and editing are free; generation uses changed goal/difficulty/adjustment and preserves draft first',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');expect(api.generate).not.toHaveBeenCalled();expect(api.run).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print("my edit")'}});
 fireEvent.change(screen.getByLabelText('练习学习目标'),{target:{value:'Check a counterexample'}});
 fireEvent.change(screen.getByLabelText('练习难度'),{target:{value:'advanced'}});
 fireEvent.change(screen.getByLabelText('练习调整要求'),{target:{value:'Add a zero input'}});
 expect(api.generate).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'按目标生成练习'}));
 await screen.findByText('Adjusted task');
 expect(api.save).toHaveBeenCalledWith('space1','p1',expect.objectContaining({code:'print("my edit")'}),expect.any(AbortSignal));
 expect(api.generate).toHaveBeenCalledWith('space1','n1',expect.objectContaining({goal:'Check a counterexample',difficulty:'advanced',adjustment:'Add a zero input',previous_practice_id:'p1'}),expect.any(AbortSignal));
 expect(api.save.mock.invocationCallOrder[0]).toBeLessThan(api.generate.mock.invocationCallOrder[0]);
 expect(JSON.parse(localStorage.getItem('paperstride:node-practice:space1:p1')!).code).toBe('print("my edit")');
});
test('running uses the edited code and input, reports real output without generation, and supports cancel',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print(inputs["x"]*3)'}});
 fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{"x":4}'}});
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 expect(api.run).toHaveBeenCalledWith('print(inputs["x"]*3)',{x:4},'',expect.any(Object));expect(api.generate).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'停止运行'}));expect(api.cancel).toHaveBeenCalledOnce();
 act(()=>api.run.mock.calls[0][3].onComplete({status:'error',output:'ZeroDivisionError',elapsed_ms:20,passed:null}));
 await screen.findByText('运行报错');expect(screen.getAllByText('ZeroDivisionError').length).toBeGreaterThan(0);
 await waitFor(()=>expect(api.record).toHaveBeenCalledWith('space1','p1',expect.objectContaining({status:'error',checked:false,code:'print(inputs["x"]*3)',input_json:'{"x":4}'})));
});
test('bad JSON is actionable and never starts a worker',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{bad'}});fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('输入不是有效 JSON，请修正后再运行。');expect(api.run).not.toHaveBeenCalled();
});

test('plotting helper is appended without losing work and renders actual worker output',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print("keep my work")'}});
 fireEvent.click(screen.getByText('让运行结果显示为图表',{selector:'summary'}));fireEvent.click(screen.getByRole('button',{name:'追加可运行绘图示例'}));
 expect((screen.getByLabelText('节点练习 Python 代码') as HTMLTextAreaElement).value).toContain('print("keep my work")');
 expect((screen.getByLabelText('节点练习 Python 代码') as HTMLTextAreaElement).value).toContain('PAPERSTRIDE_VISUAL:');
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 const output='PAPERSTRIDE_VISUAL:'+JSON.stringify({type:'line',title:'实际输出曲线',series:[{name:'y',points:[[0,0],[1,2]]}]});
 act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output,elapsed_ms:30,passed:null}));
 expect((await screen.findAllByRole('img',{name:'实际输出曲线'}))[0]).toBeVisible();expect(api.generate).not.toHaveBeenCalled();
 await waitFor(()=>expect(api.record).toHaveBeenCalledWith('space1','p1',expect.objectContaining({output,status:'success'})));
});
test('an unmounted or changed node terminates its runtime and ignores late output',async()=>{
 const view=render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 const callback=api.run.mock.calls[0][3];view.unmount();expect(api.cancel).toHaveBeenCalledOnce();callback.onComplete({status:'success',output:'late',elapsed_ms:100,passed:null});expect(api.record).not.toHaveBeenCalled();
});

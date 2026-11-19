import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import type {KnowledgePracticeArtifact} from '../api/knowledgePractice';
import KnowledgePractice from '../components/knowledge/KnowledgePractice';
import {AccessModeProvider} from '../components/SessionContext';

const api=vi.hoisted(()=>({get:vi.fn(),generate:vi.fn(),version:vi.fn(),save:vi.fn(),record:vi.fn(),review:vi.fn(),experience:vi.fn(),run:vi.fn(),cancel:vi.fn(),mappings:vi.fn()}));
vi.mock('../api/knowledgePractice',()=>({getNodePractice:api.get,generateNodePractice:api.generate,getPracticeVersion:api.version,savePracticeDraft:api.save,recordPracticeRun:api.record,reviewPracticeCode:api.review,savePracticeExperience:api.experience,getPracticeMappings:api.mappings}));
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
function task(name:string){fireEvent.click(within(screen.getByRole('tablist',{name:'练习任务分区'})).getByRole('tab',{name}));}
beforeEach(()=>{vi.clearAllMocks();localStorage.clear();api.get.mockResolvedValue(artifact());api.generate.mockResolvedValue({...artifact('p2'),status:'ready',title:'Adjusted task'});api.save.mockImplementation((_p,_id,body)=>Promise.resolve({...artifact(),draft_code:body.code,input_json:body.input_json,revision:2}));api.record.mockImplementation((_p,id,body)=>Promise.resolve({...body,id:'r1',practice_id:id,created_at:'now',origin:'browser_teaching_run'}));api.run.mockImplementation((_code,_inputs,_tests,callbacks)=>{callbacks.onState('running');return {cancel:api.cancel}})});

test('no node only guides selection and never requests a course',()=>{
 render(<KnowledgePractice projectId="space1" onBack={vi.fn()}/>);
 expect(screen.getByRole('heading',{name:'选择一个知识节点开始练习'})).toBeVisible();expect(api.get).not.toHaveBeenCalled();expect(api.generate).not.toHaveBeenCalled();
});
test('saved history is accessible on reopening before running again',async()=>{
 const run={id:'r1',practice_id:'p1',status:'success',output:'42',code:'print(42)',input_json:'{}',elapsed_ms:20,checked:true,passed:true,created_at:'now',origin:'browser_teaching_run',verification:'browser_reported_not_independently_verified'} as const;
 api.get.mockResolvedValue({...artifact(),runs:[run]});
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');task('学习记录');
 expect(await screen.findByText('最近运行记录（1）')).toBeVisible();
 fireEvent.click(screen.getByText('最近运行记录（1）'));
 expect(screen.getByText('教学运行完成 · 20 ms · 检查通过')).toBeVisible();
});
test('an intentionally empty saved draft stays empty after reopening',async()=>{
 api.get.mockResolvedValue({...artifact(),draft_code:''});
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 expect(await screen.findByLabelText('节点练习 Python 代码')).toHaveValue('');
});
test('requests model feedback with the current code only on user action',async()=>{
 api.review.mockResolvedValue({feedback:'检查张量的维度。'});
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'import torch'}});
 fireEvent.click(screen.getByRole('button',{name:'AI 分析代码'}));
 expect(await screen.findByRole('heading',{name:'AI 代码分析'})).toBeVisible();
 expect(api.review).toHaveBeenCalledWith('space1','p1',{code:'import torch',output:''},expect.any(AbortSignal));
});
test('saving AI feedback requires explicit confirmation and uses edited content',async()=>{
 api.review.mockResolvedValue({feedback:'检查张量的维度。'});
 api.experience.mockResolvedValue({content:'核对张量维度与输入。'});
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'AI 分析代码'}));
 await screen.findByRole('heading',{name:'AI 代码分析'});
 expect(api.experience).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('保存到经验库'));
 fireEvent.change(screen.getByLabelText('经验内容'),{target:{value:'核对张量维度与输入。'}});
 fireEvent.click(screen.getByRole('button',{name:'确认保存经验'}));
 await waitFor(()=>expect(api.experience).toHaveBeenCalledWith('space1','n1',{content:'核对张量维度与输入。',practice_id:'p1'},expect.any(AbortSignal)));
 expect(await screen.findByRole('button',{name:'已保存'})).toBeDisabled();
});
test('experience save failure keeps edited feedback available for retry',async()=>{
 api.review.mockResolvedValue({feedback:'检查张量维度。'});
 api.experience.mockRejectedValue(new Error('保存失败'));
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'AI 分析代码'}));
 await screen.findByRole('heading',{name:'AI 代码分析'});
 fireEvent.click(screen.getByText('保存到经验库'));
 fireEvent.click(screen.getByRole('button',{name:'确认保存经验'}));
 await waitFor(()=>expect(screen.getAllByRole('alert').some(item=>item.textContent?.includes('保存失败'))).toBe(true));
 expect(screen.getByLabelText('经验内容')).toHaveValue('检查张量维度。');
 expect(screen.getByRole('button',{name:'确认保存经验'})).toBeEnabled();
});
test('account switches do not expose or overwrite another account draft',async()=>{
 const userA={id:'a',username:'a',role:'user'},userB={id:'b',username:'b',role:'user'};
 const page=(user:typeof userA)=><AccessModeProvider mode="multiuser" user={user}><KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/></AccessModeProvider>;
 const view=render(page(userA));
 await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print("private A")'}});
 view.rerender(page(userB));
 await waitFor(()=>expect(screen.getByLabelText('节点练习 Python 代码')).toHaveValue('print(inputs["x"])'));
 expect(localStorage.getItem('paperstride:node-practice:account:a:space1:p1')).toContain('private A');
 expect(localStorage.getItem('paperstride:node-practice:account:b:space1:p1')||'').not.toContain('private A');
 view.rerender(page(userA));
 await waitFor(()=>expect(screen.getByLabelText('节点练习 Python 代码')).toHaveValue('print("private A")'));
});
test('switching projects does not write the old project draft into the new project',async()=>{
 const user={id:'a',username:'a',role:'user'};
 const page=(project:string)=><AccessModeProvider mode="multiuser" user={user}><KnowledgePractice projectId={project} nodeId="n1" onBack={vi.fn()}/></AccessModeProvider>;
 const view=render(page('space1'));
 await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print("project one")'}});
 view.rerender(page('space2'));
 await waitFor(()=>expect(screen.getByLabelText('节点练习 Python 代码')).toHaveValue('print(inputs["x"])'));
 expect(localStorage.getItem('paperstride:node-practice:account:a:space2:p1')||'').not.toContain('project one');
});
test('newer server revision cannot be overwritten by an older local draft',async()=>{
 localStorage.setItem('paperstride:node-practice:space1:p1',JSON.stringify({code:'print("unsaved")',input_json:'{}',revision:1}));
 api.get.mockResolvedValue({...artifact(),revision:2,draft_code:'print("server")'});
 api.save.mockRejectedValue(new Error('409 练习编辑稿已更新'));
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 expect(await screen.findByLabelText('节点练习 Python 代码')).toHaveValue('print("unsaved")');
 expect(screen.getByRole('button',{name:'使用服务端版本'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'保存编辑稿'}));
 await waitFor(()=>expect(api.save).toHaveBeenCalledWith('space1','p1',expect.objectContaining({expected_revision:1,code:'print("unsaved")'}),expect.any(AbortSignal)));
 fireEvent.click(screen.getByRole('button',{name:'使用服务端版本'}));
 expect(screen.getByLabelText('节点练习 Python 代码')).toHaveValue('print("server")');
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
 task('设置');
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
 expect(localStorage.getItem('paperstride:node-practice:space1:p1')).toBeNull();
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
test('submission immediately shows the result and explains its scope',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'提交并检查'}));
 expect(api.run).toHaveBeenCalledWith(expect.any(String),expect.any(Object),'assert inputs["x"] == 2',expect.any(Object));
 act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output:'2',elapsed_ms:20,passed:true}));
 expect(await screen.findByRole('heading',{name:'提交检查通过'})).toBeVisible();
 expect(screen.getByText('检查基于当前输入与题目提供的检查条件。')).toBeVisible();
});
test('failed submission shows failed status without reporting mastery',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'提交并检查'}));
 act(()=>api.run.mock.calls[0][3].onComplete({status:'error',output:'AssertionError: 结果不正确',elapsed_ms:20,passed:false}));
 expect(await screen.findByRole('heading',{name:'提交检查未通过'})).toBeVisible();
 expect(screen.getAllByText('AssertionError: 结果不正确').length).toBeGreaterThan(0);
});
test('bad JSON is actionable and never starts a worker',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{bad'}});fireEvent.click(screen.getByRole('button',{name:'运行代码'}));
 await waitFor(()=>expect(screen.getAllByRole('alert').some(alert=>alert.textContent?.includes('输入不是有效 JSON，请修正后再运行。'))).toBe(true));expect(api.run).not.toHaveBeenCalled();
});

test('plotting helper is appended without losing work and renders actual worker output',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.change(screen.getByLabelText('节点练习 Python 代码'),{target:{value:'print("keep my work")'}});
 task('输入');
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


test('a selected correspondence is bound before loading and when generating an exercise',async()=>{
 const mapping={id:'mapping-1',revision:3,status:'confirmed',stale:false,implementation_kind:'teaching',paper_span:'divide by sqrt(d_k)',code_span:'score / sqrt(d_k)'};
 api.mappings.mockResolvedValue({items:[mapping]});
 api.get.mockResolvedValue({...artifact(),mapping_id:mapping.id,mapping_revision:3,mapping_snapshot:mapping});
 render(<KnowledgePractice projectId="space1" nodeId="n1" mappingId={mapping.id} onBack={vi.fn()}/>);
 await screen.findByText('Scale starter');
 expect(api.get).toHaveBeenCalledWith('space1','n1',expect.objectContaining({mapping_id:'mapping-1',mapping_revision:3}),expect.any(AbortSignal));
 task('设置');
 fireEvent.click(screen.getByRole('button',{name:'按目标生成练习'}));
 await waitFor(()=>expect(api.generate).toHaveBeenCalledWith('space1','n1',expect.objectContaining({mapping_id:'mapping-1',mapping_revision:3}),expect.any(AbortSignal)));
});

test('task and result changes retain the same code editor and input draft',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 const editor=screen.getByLabelText('节点练习 Python 代码');fireEvent.change(editor,{target:{value:'print(inputs["x"]*3)'}});
 task('输入');fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{"x":4}'}});task('设置');task('输入');
 expect(screen.getByLabelText('练习输入 JSON')).toHaveValue('{"x":4}');expect(screen.getByLabelText('节点练习 Python 代码')).toBe(editor);
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output:'12',elapsed_ms:20,passed:null}));
 expect(await screen.findByRole('heading',{name:'教学运行完成'})).toBeVisible();expect(screen.getByLabelText('节点练习 Python 代码')).toBe(editor);expect(editor).toHaveValue('print(inputs["x"]*3)');
});

test('stdin and JSON stay synchronized and invalid JSON is never overwritten',async()=>{
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');task('输入');
 fireEvent.change(screen.getByLabelText('程序输入'),{target:{value:'5\n6'}});expect(JSON.parse((screen.getByLabelText('练习输入 JSON') as HTMLTextAreaElement).value).stdin).toEqual(['5','6']);
 fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{"stdin":["9","10"],"x":7}'}});expect(screen.getByLabelText('程序输入')).toHaveValue('9\n10');
 fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{broken'}});fireEvent.change(screen.getByLabelText('程序输入'),{target:{value:'do not discard JSON'}});expect(screen.getByLabelText('练习输入 JSON')).toHaveValue('{broken');expect(api.run).not.toHaveBeenCalled();
});

test('AI review does not attach output from a different input draft',async()=>{
 api.review.mockResolvedValue({feedback:'核对当前输入。'});render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output:'2',elapsed_ms:20,passed:null}));
 task('输入');fireEvent.change(screen.getByLabelText('练习输入 JSON'),{target:{value:'{"x":99}'}});fireEvent.click(screen.getByRole('button',{name:'AI 分析代码'}));
 await waitFor(()=>expect(api.review).toHaveBeenCalledWith('space1','p1',{code:'print(inputs["x"])',output:''},expect.any(AbortSignal)));
});

test('switching practice versions clears the previous run explanation binding',async()=>{
 const mapping={id:'mapping-1',revision:3,status:'confirmed',stale:false,implementation_kind:'teaching',paper_span:'scale',code_span:'scale'};
 const first={...artifact(),mapping_snapshot:mapping},second={...artifact('p2'),mapping_snapshot:mapping};first.versions=[...first.versions,...second.versions];second.versions=first.versions;
 api.get.mockResolvedValue(first);api.version.mockResolvedValue(second);
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');fireEvent.click(screen.getByRole('button',{name:'运行代码'}));act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output:'2',elapsed_ms:20,passed:null}));
 await screen.findByRole('button',{name:'保存运行解释'});fireEvent.change(screen.getByLabelText('运行后的解释'),{target:{value:'旧版本解释'}});
 fireEvent.change(screen.getByLabelText('练习版本'),{target:{value:'p2'}});await waitFor(()=>expect(api.version).toHaveBeenCalledWith('space1','p2',expect.any(AbortSignal)));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'保存运行解释'})).toBeNull());expect(screen.queryByLabelText('运行后的解释')).toBeNull();
});

test('stale mappings keep execution disabled with a visible reason',async()=>{
 api.get.mockResolvedValue({...artifact(),mapping_snapshot:{id:'old',revision:1,status:'confirmed',stale:true,implementation_kind:'teaching',paper_span:'scale',code_span:'scale'},mapping_stale:true});
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 expect(screen.getByRole('button',{name:'运行代码'})).toBeDisabled();expect(screen.getByRole('button',{name:'提交并检查'})).toBeDisabled();expect(screen.getAllByRole('alert').find(item=>item.textContent?.includes('关联的论文与代码对应已变化，请先重新核对。'))).toBeVisible();
});

test('a delayed run save cannot bind its explanation to another practice version',async()=>{
 const mapping={id:'mapping-1',revision:3,status:'confirmed',stale:false,implementation_kind:'teaching',paper_span:'scale',code_span:'scale'};
 const first={...artifact(),mapping_snapshot:mapping},second={...artifact('p2'),mapping_snapshot:mapping};first.versions=[...first.versions,...second.versions];second.versions=first.versions;
 let resolveOld!:(value:unknown)=>void;
 api.record.mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve}));api.get.mockResolvedValue(first);api.version.mockResolvedValue(second);
 render(<KnowledgePractice projectId="space1" nodeId="n1" onBack={vi.fn()}/>);await screen.findByText('Scale starter');
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));act(()=>api.run.mock.calls[0][3].onComplete({status:'success',output:'2',elapsed_ms:20,passed:null}));
 fireEvent.change(screen.getByLabelText('练习版本'),{target:{value:'p2'}});await waitFor(()=>expect(screen.getByLabelText('练习版本')).toHaveValue('p2'));
 fireEvent.click(screen.getByRole('button',{name:'运行代码'}));await act(async()=>{resolveOld({id:'old-run',practice_id:'p1',output:'2'})});
 expect(screen.queryByRole('button',{name:'保存运行解释'})).toBeNull();
});

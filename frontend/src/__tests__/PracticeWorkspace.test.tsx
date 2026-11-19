import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import PracticeWorkspace,{practiceWorkspaceKey,type PracticeWorkspaceProps} from '../components/knowledge/PracticeWorkspace';

const session=vi.hoisted(()=>({account:{id:'account-a'}}));
vi.mock('../components/SessionContext',()=>({useCurrentAccount:()=>session.account}));
let width=1000,top=180,actionsHeight=48;
let observers:(()=>void)[]=[];
beforeEach(()=>{
 localStorage.clear();session.account={id:'account-a'};width=1000;top=180;actionsHeight=48;observers=[];
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  const height=this.classList.contains('kw-practice-ide-actions')?actionsHeight:this.classList.contains('kw-practice-ide-editor-toolbar')?36:568;
  return{width,height,top,bottom:top+height,left:0,right:width,x:0,y:top,toJSON:()=>({})};
 });
 vi.stubGlobal('ResizeObserver',class{constructor(callback:()=>void){observers.push(callback)}observe(){}disconnect(){}});
 Object.defineProperty(window,'innerHeight',{configurable:true,value:768});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
function props(overrides:Partial<PracticeWorkspaceProps>={}):PracticeWorkspaceProps{
 return{projectId:'p',nodeId:'n',instructions:<p>当前教学题面。</p>,input:<textarea aria-label="练习输入" defaultValue="初始输入"/>,history:<p>已保存的运行记录。</p>,settings:<input aria-label="练习目标" defaultValue="初始目标"/>,editor:<textarea aria-label="节点练习 Python 代码" defaultValue="print(1)"/>,editorToolbar:<span>Python</span>,actions:<button>运行代码</button>,output:<p>运行后在这里显示输出。</p>,analysis:<textarea aria-label="经验内容" defaultValue=""/>,...overrides};
}
const taskSeparator=()=>screen.getByRole('separator',{name:'调整任务栏宽度'});
const resultSeparator=()=>screen.getByRole('separator',{name:'调整结果区高度'});
const key=(project='p',node='n',account='account-a')=>practiceWorkspaceKey(account,project,node);
const notify=()=>act(()=>observers.forEach(callback=>callback()));

test('the desktop workspace gives code the main area and keeps a single action bar with idle results',()=>{
 const ui=render(<PracticeWorkspace {...props()}/>);
 expect(taskSeparator()).toHaveAttribute('aria-valuenow','300');
 expect(taskSeparator()).toHaveAttribute('aria-valuemin','260');
 expect(taskSeparator()).toHaveAttribute('aria-valuemax','380');
 expect(resultSeparator()).toHaveAttribute('aria-valuenow','180');
 expect(resultSeparator()).toHaveAttribute('aria-valuemax','290');
 expect(ui.container.querySelector('.kw-practice-ide')).toHaveStyle({height:'568px'});
 expect(screen.getByRole('tabpanel',{name:'题目'})).toHaveTextContent('当前教学题面。');
 expect(screen.getByRole('tabpanel',{name:'运行结果'})).toHaveTextContent('运行后在这里显示输出。');
 expect(screen.getAllByRole('button',{name:'运行代码'})).toHaveLength(1);
 expect(screen.getByRole('textbox',{name:'节点练习 Python 代码'})).toBeVisible();
 expect(localStorage.getItem(key())).toBeNull();
});

test('tabs preserve input, settings and editor DOM while output appears and sizes change',()=>{
 const ui=render(<PracticeWorkspace {...props()}/>);
 const editor=screen.getByRole('textbox',{name:'节点练习 Python 代码'});
 fireEvent.change(editor,{target:{value:'print("unsaved")'}});
 fireEvent.click(screen.getByRole('tab',{name:'输入'}));
 const input=screen.getByRole('textbox',{name:'练习输入'});fireEvent.change(input,{target:{value:'尚未运行的输入'}});
 fireEvent.click(screen.getByRole('tab',{name:'设置'}));
 const goal=screen.getByRole('textbox',{name:'练习目标'});fireEvent.change(goal,{target:{value:'未提交的目标'}});
 fireEvent.click(screen.getByRole('tab',{name:'题目'}));
 fireEvent.keyDown(taskSeparator(),{key:'ArrowRight'});fireEvent.keyDown(resultSeparator(),{key:'ArrowUp'});
 ui.rerender(<PracticeWorkspace {...props({output:<p>本次输出：1</p>})}/>);
 expect(screen.getByRole('textbox',{name:'节点练习 Python 代码'})).toBe(editor);
 expect(editor).toHaveValue('print("unsaved")');
 fireEvent.click(screen.getByRole('tab',{name:'输入'}));expect(screen.getByRole('textbox',{name:'练习输入'})).toBe(input);expect(input).toHaveValue('尚未运行的输入');
 fireEvent.click(screen.getByRole('tab',{name:'设置'}));expect(screen.getByRole('textbox',{name:'练习目标'})).toBe(goal);expect(goal).toHaveValue('未提交的目标');
 expect(screen.getByRole('tabpanel',{name:'运行结果'})).toHaveTextContent('本次输出：1');
});

test('keyboard separators adjust in the expected direction, enforce limits and reset each dimension independently',()=>{
 render(<PracticeWorkspace {...props()}/>);
 fireEvent.keyDown(taskSeparator(),{key:'ArrowRight'});expect(taskSeparator()).toHaveAttribute('aria-valuenow','316');
 fireEvent.keyDown(taskSeparator(),{key:'ArrowLeft',shiftKey:true});expect(taskSeparator()).toHaveAttribute('aria-valuenow','268');
 fireEvent.keyDown(taskSeparator(),{key:'Home'});expect(taskSeparator()).toHaveAttribute('aria-valuenow','260');
 fireEvent.keyDown(taskSeparator(),{key:'End'});expect(taskSeparator()).toHaveAttribute('aria-valuenow','380');
 fireEvent.keyDown(resultSeparator(),{key:'ArrowUp'});expect(resultSeparator()).toHaveAttribute('aria-valuenow','196');
 fireEvent.keyDown(resultSeparator(),{key:'ArrowDown',shiftKey:true});expect(resultSeparator()).toHaveAttribute('aria-valuenow','148');
 fireEvent.keyDown(resultSeparator(),{key:'Home'});expect(resultSeparator()).toHaveAttribute('aria-valuenow','100');
 fireEvent.keyDown(resultSeparator(),{key:'End'});expect(resultSeparator()).toHaveAttribute('aria-valuenow','290');
 expect(JSON.parse(localStorage.getItem(key())!)).toEqual({sidebarWidth:380,resultHeight:290});
 fireEvent.keyDown(taskSeparator(),{key:'Enter'});expect(taskSeparator()).toHaveAttribute('aria-valuenow','300');
 expect(JSON.parse(localStorage.getItem(key())!)).toEqual({resultHeight:290});
 fireEvent.doubleClick(resultSeparator());expect(resultSeparator()).toHaveAttribute('aria-valuenow','180');expect(localStorage.getItem(key())).toBeNull();
});

test('pointer resizing keeps preferences transient until the drag ends',()=>{
 render(<PracticeWorkspace {...props()}/>);
 const pointer=(element:HTMLElement,event:string,x:number,y:number)=>fireEvent(element,Object.assign(new Event(event,{bubbles:true}),{pointerId:1,button:0,clientX:x,clientY:y}));
 pointer(taskSeparator(),'pointerdown',300,0);pointer(taskSeparator(),'pointermove',350,0);
 expect(taskSeparator()).toHaveAttribute('aria-valuenow','350');expect(localStorage.getItem(key())).toBeNull();
 pointer(taskSeparator(),'pointerup',350,0);expect(JSON.parse(localStorage.getItem(key())!)).toEqual({sidebarWidth:350});
 pointer(resultSeparator(),'pointerdown',0,500);pointer(resultSeparator(),'pointermove',0,450);
 expect(resultSeparator()).toHaveAttribute('aria-valuenow','230');expect(JSON.parse(localStorage.getItem(key())!)).toEqual({sidebarWidth:350});
 pointer(resultSeparator(),'pointerup',0,450);expect(JSON.parse(localStorage.getItem(key())!)).toEqual({sidebarWidth:350,resultHeight:230});
});

test('sizes are isolated by account, project and node, and restore when reopening that scope',()=>{
 const ui=render(<PracticeWorkspace {...props()}/>);
 fireEvent.keyDown(taskSeparator(),{key:'End'});fireEvent.keyDown(resultSeparator(),{key:'End'});
 ui.rerender(<PracticeWorkspace {...props({nodeId:'other'})}/>);expect(taskSeparator()).toHaveAttribute('aria-valuenow','300');expect(resultSeparator()).toHaveAttribute('aria-valuenow','180');
 ui.rerender(<PracticeWorkspace {...props({projectId:'other'})}/>);expect(taskSeparator()).toHaveAttribute('aria-valuenow','300');
 session.account={id:'account-b'};ui.rerender(<PracticeWorkspace {...props()}/>);expect(taskSeparator()).toHaveAttribute('aria-valuenow','300');
 session.account={id:'account-a'};ui.rerender(<PracticeWorkspace {...props()}/>);expect(taskSeparator()).toHaveAttribute('aria-valuenow','380');expect(resultSeparator()).toHaveAttribute('aria-valuenow','290');
 expect(localStorage.getItem(key('p','other'))).toBeNull();expect(localStorage.getItem(key('other'))).toBeNull();expect(localStorage.getItem(key('p','n','account-b'))).toBeNull();
});

test('viewport and wrapped actions clamp the display without overwriting the preferred layout',()=>{
 localStorage.setItem(key(),JSON.stringify({sidebarWidth:370,resultHeight:270}));
 const ui=render(<PracticeWorkspace {...props()}/>),editor=screen.getByRole('textbox',{name:'节点练习 Python 代码'});
 width=800;Object.defineProperty(window,'innerHeight',{configurable:true,value:640});actionsHeight=80;notify();
 expect(taskSeparator()).toHaveAttribute('aria-valuenow','308');expect(resultSeparator()).toHaveAttribute('aria-valuemax','130');expect(resultSeparator()).toHaveAttribute('aria-valuenow','130');
 expect(JSON.parse(localStorage.getItem(key())!)).toEqual({sidebarWidth:370,resultHeight:270});
 width=1000;actionsHeight=48;Object.defineProperty(window,'innerHeight',{configurable:true,value:768});notify();
 expect(taskSeparator()).toHaveAttribute('aria-valuenow','370');expect(resultSeparator()).toHaveAttribute('aria-valuenow','270');expect(screen.getByRole('textbox',{name:'节点练习 Python 代码'})).toBe(editor);
 const height=ui.container.querySelector('.kw-practice-ide')?.getAttribute('style');notify();expect(ui.container.querySelector('.kw-practice-ide')?.getAttribute('style')).toBe(height);
});

test('new focus nonces select the requested panel without overriding later manual navigation or losing drafts',()=>{
 const ui=render(<PracticeWorkspace {...props({resultFocus:{tab:'output',nonce:1}})}/>);
 fireEvent.click(screen.getByRole('tab',{name:'AI 分析'}));
 const experience=screen.getByRole('textbox',{name:'经验内容'});fireEvent.change(experience,{target:{value:'待保存的分析'}});
 ui.rerender(<PracticeWorkspace {...props({resultFocus:{tab:'output',nonce:1}})}/>);expect(screen.getByRole('tab',{name:'AI 分析'})).toHaveAttribute('aria-selected','true');
 ui.rerender(<PracticeWorkspace {...props({resultFocus:{tab:'output',nonce:2},taskFocus:{tab:'settings',nonce:1}})}/>);
 expect(screen.getByRole('tab',{name:'运行结果'})).toHaveAttribute('aria-selected','true');expect(screen.getByRole('tab',{name:'设置'})).toHaveAttribute('aria-selected','true');
 ui.rerender(<PracticeWorkspace {...props({resultFocus:{tab:'analysis',nonce:3},taskFocus:{tab:'instructions',nonce:2}})}/>);
 expect(screen.getByRole('tab',{name:'题目'})).toHaveAttribute('aria-selected','true');expect(screen.getByRole('textbox',{name:'经验内容'})).toBe(experience);expect(experience).toHaveValue('待保存的分析');
});

test('tab keyboard navigation moves focus while leaving editor Tab handling to the parent',()=>{
 render(<PracticeWorkspace {...props()}/>);
 const taskTabs=within(screen.getByRole('tablist',{name:'练习任务分区'}));
 fireEvent.keyDown(taskTabs.getByRole('tab',{name:'题目'}),{key:'ArrowRight'});expect(taskTabs.getByRole('tab',{name:'输入'})).toHaveFocus();
 fireEvent.keyDown(taskTabs.getByRole('tab',{name:'输入'}),{key:'End'});expect(taskTabs.getByRole('tab',{name:'设置'})).toHaveFocus();
 const resultTabs=within(screen.getByRole('tablist',{name:'练习结果分区'}));
 fireEvent.keyDown(resultTabs.getByRole('tab',{name:'运行结果'}),{key:'ArrowRight'});expect(resultTabs.getByRole('tab',{name:'AI 分析'})).toHaveFocus();
 const event=new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true});fireEvent(screen.getByRole('textbox',{name:'节点练习 Python 代码'}),event);expect(event.defaultPrevented).toBe(false);
});

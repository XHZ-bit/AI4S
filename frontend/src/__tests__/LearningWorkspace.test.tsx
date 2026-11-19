import {useState} from 'react';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import LearningWorkspace,{learningWorkspaceLayoutKey,type LearningToolTab} from '../components/knowledge/LearningWorkspace';
import LearningEvidence from '../components/knowledge/LearningEvidence';
import type {KnowledgeEvidence,KnowledgeNode} from '../api/knowledge';

const account=vi.hoisted(()=>({value:{id:'a'}}));
vi.mock('../components/SessionContext',()=>({useCurrentAccount:()=>account.value}));
vi.mock('../components/knowledge/LearningProgress',()=>({default:({children,summaryVisible,onOpenSummary}:any)=><div><label>状态<select aria-label="我的学习状态"><option>待学习</option></select></label><button onClick={onOpenSummary}>查看学习小结</button>{children}<section role="tabpanel" id="kw-learning-tool-records-panel" aria-labelledby="kw-learning-tool-records-tab" hidden={!summaryVisible}>已保存的学习小结</section></div>}));
vi.mock('../components/knowledge/KnowledgeText',()=>({default:({text}:{text:string})=><p>{text}</p>}));
vi.mock('antd',()=>({Button:({children,size:_,...props}:any)=><button {...props}>{children}</button>}));
let width=1000,top=180,observers:(()=>void)[]=[];
beforeEach(()=>{
 sessionStorage.clear();localStorage.clear();account.value={id:'a'};width=1000;top=180;observers=[];
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>({width,height:500,top,bottom:top+500,left:0,right:width,x:0,y:top,toJSON:()=>({})}));
 vi.stubGlobal('ResizeObserver',class{constructor(callback:()=>void){observers.push(callback)}observe(){}disconnect(){}});
 Object.defineProperty(window,'innerHeight',{configurable:true,value:768});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();Reflect.deleteProperty(document,'fullscreenElement')});
function Harness({nodeId='n',projectId='p',focusResources=false}:{nodeId?:string;projectId?:string;focusResources?:boolean}) {
 const [tool,setTool]=useState<LearningToolTab>('question');
 return <LearningWorkspace projectId={projectId} nodeId={nodeId} focusResources={focusResources} tool={tool} onTool={setTool} onNode={vi.fn()} chapters={[{id:'chapter',label:'公式与推导'}]} lesson={<section id="chapter" tabIndex={-1}><h3>可读讲解</h3><textarea aria-label="讲解草稿"/></section>} evidence={<p>独立证据内容</p>} practice={<details id="kw-learning-resources"><summary>学习资料</summary>资源正文</details>} question={<input aria-label="提问草稿"/>} notes={<textarea aria-label="笔记草稿"/>}/>;
}
const main=(name:string)=>within(screen.getByRole('tablist',{name:'学习阅读分区'})).getByRole('tab',{name});
const tools=(name:string)=>within(screen.getByRole('tablist',{name:'随手学习工具分区'})).getByRole('tab',{name});
test('read areas and tool areas are independent and retain unsaved content',()=>{
 render(<Harness/>);fireEvent.change(screen.getByLabelText('讲解草稿'),{target:{value:'未保存的推导'}});fireEvent.change(screen.getByLabelText('提问草稿'),{target:{value:'为什么除以维度平方根？'}});
 fireEvent.click(main('原文依据'));expect(screen.getByText('独立证据内容')).toBeVisible();expect(screen.getByLabelText('讲解草稿')).not.toBeVisible();
 fireEvent.click(tools('笔记'));fireEvent.change(screen.getByLabelText('笔记草稿'),{target:{value:'我区分了分数和权重'}});
 fireEvent.click(main('讲解'));expect(screen.getByLabelText('讲解草稿')).toHaveValue('未保存的推导');
 fireEvent.click(tools('提问'));expect(screen.getByLabelText('提问草稿')).toHaveValue('为什么除以维度平方根？');
 fireEvent.click(tools('笔记'));expect(screen.getByLabelText('笔记草稿')).toHaveValue('我区分了分数和权重');
});
test('a summary opens next to the same reading position',()=>{
 render(<Harness/>);const pane=screen.getByRole('tabpanel',{name:'讲解'});pane.scrollTop=420;fireEvent.scroll(pane);
 fireEvent.click(screen.getByRole('button',{name:'查看学习小结'}));expect(tools('学习记录')).toHaveAttribute('aria-selected','true');expect(screen.getByText('已保存的学习小结')).toBeVisible();expect(pane.scrollTop).toBe(420);
});
test('reader tab and scroll restore by node and account after a source roundtrip',()=>{
 const ui=render(<Harness/>);fireEvent.click(main('原文依据'));const pane=screen.getByRole('tabpanel',{name:'原文依据'});pane.scrollTop=360;fireEvent.scroll(pane);ui.unmount();
 const reopen=render(<Harness/>);expect(main('原文依据')).toHaveAttribute('aria-selected','true');expect(screen.getByRole('tabpanel',{name:'原文依据'}).scrollTop).toBe(360);
 reopen.rerender(<Harness nodeId="other"/>);expect(main('讲解')).toHaveAttribute('aria-selected','true');
 account.value={id:'b'};reopen.rerender(<Harness/>);expect(main('讲解')).toHaveAttribute('aria-selected','true');
});
test('keyboard tabs expose their current panel and focus',()=>{
 render(<Harness/>);fireEvent.keyDown(main('讲解'),{key:'ArrowRight'});expect(main('原文依据')).toHaveFocus();expect(screen.getByRole('tabpanel',{name:'原文依据'})).toBeVisible();
 fireEvent.keyDown(tools('提问'),{key:'End'});expect(tools('学习记录')).toHaveFocus();expect(screen.getByText('已保存的学习小结')).toBeVisible();
});
test('the resource deep link opens resources in its own scroll panel',async()=>{
 render(<Harness focusResources/>);expect(main('练习与实现')).toHaveAttribute('aria-selected','true');await waitFor(()=>expect(document.getElementById('kw-learning-resources')).toHaveAttribute('open'));
});
const separator=()=>screen.getByRole('separator',{name:'调整学习工具宽度'});
const layoutKey=(project='p',user='a')=>learningWorkspaceLayoutKey(user,project);
test('tool resizing reserves 600px for reading, supports keyboard reset and remembers only explicit changes',()=>{
 render(<Harness/>);
 expect(separator()).toHaveAttribute('aria-valuenow','320');expect(separator()).toHaveAttribute('aria-valuemin','280');expect(separator()).toHaveAttribute('aria-valuemax','388');
 expect(localStorage.getItem(layoutKey())).toBeNull();
 fireEvent.keyDown(separator(),{key:'ArrowLeft'});expect(separator()).toHaveAttribute('aria-valuenow','336');
 fireEvent.keyDown(separator(),{key:'ArrowRight',shiftKey:true});expect(separator()).toHaveAttribute('aria-valuenow','288');
 fireEvent.keyDown(separator(),{key:'Home'});expect(separator()).toHaveAttribute('aria-valuenow','280');
 fireEvent.keyDown(separator(),{key:'End'});expect(separator()).toHaveAttribute('aria-valuenow','388');
 fireEvent.keyDown(separator(),{key:'Enter'});expect(separator()).toHaveAttribute('aria-valuenow','320');expect(JSON.parse(localStorage.getItem(layoutKey())!).toolWidth).toBeUndefined();
});
test('pointer resizing persists on release and viewport clamping preserves the chosen width',()=>{
 width=1300;render(<Harness/>);
 const pointer=(name:string,x:number)=>fireEvent(separator(),Object.assign(new Event(name,{bubbles:true}),{pointerId:1,button:0,clientX:x}));
 pointer('pointerdown',900);pointer('pointermove',760);expect(separator()).toHaveAttribute('aria-valuenow','460');expect(localStorage.getItem(layoutKey())).toBeNull();
 pointer('pointerup',760);expect(JSON.parse(localStorage.getItem(layoutKey())!).toolWidth).toBe(460);
 width=1000;act(()=>observers.forEach(callback=>callback()));expect(separator()).toHaveAttribute('aria-valuenow','388');expect(JSON.parse(localStorage.getItem(layoutKey())!).toolWidth).toBe(460);
 width=1300;act(()=>observers.forEach(callback=>callback()));expect(separator()).toHaveAttribute('aria-valuenow','460');
 fireEvent.doubleClick(separator());expect(separator()).toHaveAttribute('aria-valuenow','320');
});
test('collapsing preserves mounted drafts and direct question, notes and summary shortcuts reopen their tool',()=>{
 render(<Harness/>);const lesson=screen.getByLabelText('讲解草稿'),question=screen.getByLabelText('提问草稿');
 fireEvent.change(lesson,{target:{value:'推导写到一半'}});fireEvent.change(question,{target:{value:'还没发送的问题'}});
 fireEvent.click(tools('笔记'));const note=screen.getByLabelText('笔记草稿');fireEvent.change(note,{target:{value:'未保存的个人理解'}});
 fireEvent.click(screen.getByRole('button',{name:'收起工具'}));expect(screen.getByRole('button',{name:'展开工具'})).toHaveAttribute('aria-expanded','false');expect(note).not.toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'打开提问工具'}));expect(tools('提问')).toHaveFocus();expect(screen.getByLabelText('提问草稿')).toBe(question);expect(question).toHaveValue('还没发送的问题');
 fireEvent.click(screen.getByRole('button',{name:'收起工具'}));fireEvent.click(screen.getByRole('button',{name:'打开笔记工具'}));expect(screen.getByLabelText('笔记草稿')).toBe(note);expect(note).toHaveValue('未保存的个人理解');
 fireEvent.click(screen.getByRole('button',{name:'收起工具'}));fireEvent.click(screen.getByRole('button',{name:'查看学习小结'}));expect(tools('学习记录')).toHaveAttribute('aria-selected','true');expect(screen.getByText('已保存的学习小结')).toBeVisible();
 expect(screen.getByLabelText('讲解草稿')).toBe(lesson);expect(lesson).toHaveValue('推导写到一半');
});
test('layout preferences are shared by nodes of a project and isolated by account and project',()=>{
 const ui=render(<Harness/>);fireEvent.keyDown(separator(),{key:'End'});fireEvent.click(screen.getByRole('button',{name:'收起工具'}));
 ui.rerender(<Harness nodeId="other"/>);expect(screen.getByRole('button',{name:'展开工具'})).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'展开工具'}));expect(separator()).toHaveAttribute('aria-valuenow','388');
 ui.rerender(<Harness projectId="other"/>);expect(separator()).toHaveAttribute('aria-valuenow','320');
 account.value={id:'b'};ui.rerender(<Harness/>);expect(separator()).toHaveAttribute('aria-valuenow','320');
 account.value={id:'a'};ui.rerender(<Harness/>);expect(separator()).toHaveAttribute('aria-valuenow','388');
});
test('focus mode remeasures top changes and preserves reader position across exit and source return',()=>{
 const ui=render(<Harness/>),pane=screen.getByRole('tabpanel',{name:'讲解'});pane.scrollTop=420;fireEvent.scroll(pane);
 top=76;fireEvent.click(screen.getByRole('button',{name:'专注阅读'}));expect(ui.container.querySelector('.kw-learning-workspace')).toHaveClass('is-focused');expect(ui.container.querySelector('.kw-learning-workspace')).toHaveStyle({height:'680px'});expect(pane.scrollTop).toBe(420);
 ui.unmount();const reopen=render(<Harness/>);expect(reopen.container.querySelector('.kw-learning-workspace')).toHaveClass('is-focused');expect(screen.getByRole('tabpanel',{name:'讲解'}).scrollTop).toBe(420);
 top=180;fireEvent.click(screen.getByRole('button',{name:'退出专注阅读'}));expect(reopen.container.querySelector('.kw-learning-workspace')).not.toHaveClass('is-focused');expect(reopen.container.querySelector('.kw-learning-workspace')).toHaveStyle({height:'576px'});expect(screen.getByRole('tabpanel',{name:'讲解'}).scrollTop).toBe(420);
});
test('Escape exits focus without intercepting fullscreen or an editing control',()=>{
 const ui=render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'专注阅读'}));
 Object.defineProperty(document,'fullscreenElement',{configurable:true,value:document.documentElement});const fullscreenEscape=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});fireEvent(window,fullscreenEscape);expect(fullscreenEscape.defaultPrevented).toBe(false);expect(ui.container.querySelector('.kw-learning-workspace')).toHaveClass('is-focused');
 Object.defineProperty(document,'fullscreenElement',{configurable:true,value:null});fireEvent.keyDown(screen.getByLabelText('讲解草稿'),{key:'Escape'});expect(ui.container.querySelector('.kw-learning-workspace')).toHaveClass('is-focused');
 fireEvent.keyDown(screen.getByRole('tabpanel',{name:'讲解'}),{key:'Escape'});expect(ui.container.querySelector('.kw-learning-workspace')).not.toHaveClass('is-focused');expect(screen.getByRole('button',{name:'专注阅读'})).toHaveFocus();
});
test('a narrow desktop keeps a readable pane and opens tools in the same workspace without unmounting it',()=>{
 width=840;render(<Harness/>);const lesson=screen.getByLabelText('讲解草稿');fireEvent.change(lesson,{target:{value:'保留的正文草稿'}});
 expect(screen.getByRole('button',{name:'展开工具'})).toBeVisible();expect(screen.queryByRole('separator')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'打开笔记工具'}));expect(screen.getByRole('tabpanel',{name:'笔记'})).toBeVisible();expect(screen.getByLabelText('讲解草稿')).not.toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'返回学习正文'}));expect(screen.getByLabelText('讲解草稿')).toBe(lesson);expect(lesson).toHaveValue('保留的正文草稿');expect(lesson).toBeVisible();
});
test('chapter navigation shares the reader bar and no longer applies an obsolete sticky offset',()=>{
 render(<Harness/>);const pane=screen.getByRole('tabpanel',{name:'讲解'}),target=document.getElementById('chapter')!;
 Object.defineProperty(pane,'getBoundingClientRect',{configurable:true,value:()=>({width:600,height:500,top:220,bottom:720,left:0,right:600,x:0,y:220,toJSON:()=>({})})});
 Object.defineProperty(target,'getBoundingClientRect',{configurable:true,value:()=>({width:600,height:300,top:420,bottom:720,left:0,right:600,x:0,y:420,toJSON:()=>({})})});
 pane.scrollTop=100;fireEvent.scroll(pane);const nav=screen.getByRole('navigation',{name:'学习内容目录'});expect(nav.closest('.kw-learning-reader-bar')).not.toBeNull();expect(pane.contains(nav)).toBe(false);
 fireEvent.change(screen.getByLabelText('跳转讲解章节'),{target:{value:'chapter'}});expect(pane.scrollTop).toBe(288);expect(target).toHaveFocus();
});
const node:KnowledgeNode={id:'n',project_id:'p',source_id:'s',kind:'method',label:'注意力',summary:'',parent_id:null,origin:'source',research_status:'unknown',version:1,hidden:false,source_missing:false,evidence_ids:['direct'],metadata:{}};
const evidence=(id:string,source='s',block=id):KnowledgeEvidence=>({id,source_id:source,block_id:block,source_title:'来源 '+source,quote:'片段 '+block,source_version:'v1',locator:{page:4,heading:'位置 '+block},origin:'source'});
test('evidence deduplication retains direct identity and separates retrieved context',()=>{
 render(<LearningEvidence node={node} items={[evidence('direct','s','same'),evidence('context','s','same'),evidence('another'),evidence('cross','other')]} onEvidence={vi.fn()}/>);
 expect(screen.getByRole('button',{name:'当前知识的直接依据 1'})).toHaveAttribute('aria-pressed','true');expect(screen.getByRole('button',{name:'同篇相关上下文 1'})).toBeVisible();expect(screen.getByRole('button',{name:'比较与关联来源 1'})).toBeVisible();expect(screen.getByText('片段 same')).toBeVisible();
});
test('long evidence is bounded and source return restores the visible group and expanded page',async()=>{
 const items=[evidence('direct'),...Array.from({length:16},(_,i)=>evidence('context'+i))],open=vi.fn();
 const ui=render(<LearningEvidence node={node} items={items} onEvidence={open}/>);fireEvent.click(screen.getByRole('button',{name:'同篇相关上下文 16'}));expect(document.querySelectorAll('.kw-learning-evidence-card')).toHaveLength(6);
 fireEvent.click(screen.getByRole('button',{name:/显示更多依据/}));expect(document.querySelectorAll('.kw-learning-evidence-card')).toHaveLength(12);
 const last=document.querySelectorAll<HTMLDetailsElement>('.kw-learning-evidence-card')[11];fireEvent.click(within(last).getByText('位置 context11'));await waitFor(()=>expect(last.open).toBe(true));fireEvent.click(within(last).getByRole('button',{name:'打开原文'}));expect(open).toHaveBeenCalledWith(items[12]);
 ui.unmount();render(<LearningEvidence node={node} items={items} onEvidence={open}/>);expect(screen.getByRole('button',{name:'同篇相关上下文 16'})).toHaveAttribute('aria-pressed','true');expect(document.querySelectorAll('.kw-learning-evidence-card')).toHaveLength(12);expect(document.querySelectorAll<HTMLDetailsElement>('.kw-learning-evidence-card')[11].open).toBe(true);
});

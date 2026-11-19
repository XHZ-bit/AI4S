import {act,fireEvent,render,screen,cleanup} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import GraphSplitLayout,{graphDetailWidthKey} from '../components/knowledge/GraphSplitLayout';

const session=vi.hoisted(()=>({account:{id:'a'}}));
vi.mock('../components/SessionContext',()=>({useCurrentAccount:()=>session.account}));
let width=1000;
let observers:(()=>void)[]=[];
beforeEach(()=>{
 localStorage.clear();session.account={id:'a'};width=1000;observers=[];
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>({width,height:500,top:180,bottom:680,left:0,right:width,x:0,y:180,toJSON:()=>({})}));
 vi.stubGlobal('ResizeObserver',class {constructor(callback:()=>void){observers.push(callback)}observe(){}disconnect(){}});
 Object.defineProperty(window,'innerHeight',{configurable:true,value:768});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
function view(projectId='p',onHeight=vi.fn()){
 return <GraphSplitLayout projectId={projectId} onCanvasHeight={onHeight} detail={controls=><aside><input aria-label="草稿" defaultValue=""/><button onClick={controls.onToggleExpanded}>{controls.expanded?'还原分栏':'展开节点详情'}</button><button onClick={controls.onResetWidth}>恢复默认宽度</button></aside>}><div className="kw-graph-primary">图谱</div></GraphSplitLayout>;
}
const separator=()=>screen.getByRole('separator',{name:'调整节点详情宽度'});
test('keyboard adjustments respect the available canvas and persist only explicit preferences',()=>{
 render(view());expect(separator()).toHaveAttribute('aria-valuenow','420');
 fireEvent.keyDown(separator(),{key:'ArrowLeft'});expect(separator()).toHaveAttribute('aria-valuenow','436');
 expect(JSON.parse(localStorage.getItem(graphDetailWidthKey('a','p'))!)).toBe(436);
 fireEvent.keyDown(separator(),{key:'ArrowRight',shiftKey:true});expect(separator()).toHaveAttribute('aria-valuenow','372');
 fireEvent.keyDown(separator(),{key:'Home'});expect(separator()).toHaveAttribute('aria-valuenow','320');
 fireEvent.keyDown(separator(),{key:'End'});expect(separator()).toHaveAttribute('aria-valuenow','668');
});
test('width is scoped to account and project and returns after reopening the same project',()=>{
 const ui=render(view());fireEvent.keyDown(separator(),{key:'End'});
 ui.rerender(view('other'));expect(separator()).toHaveAttribute('aria-valuenow','420');
 fireEvent.keyDown(separator(),{key:'ArrowLeft'});
 ui.rerender(view());expect(separator()).toHaveAttribute('aria-valuenow','668');
 session.account={id:'b'};ui.rerender(view());expect(separator()).toHaveAttribute('aria-valuenow','420');
 expect(localStorage.getItem(graphDetailWidthKey('b','p'))).toBeNull();
});
test('viewport clamping preserves the wider preference and reset restores the automatic width',()=>{
 localStorage.setItem(graphDetailWidthKey('a','p'),'640');render(view());
 width=720;act(()=>observers.forEach(run=>run()));expect(separator()).toHaveAttribute('aria-valuenow','388');
 expect(localStorage.getItem(graphDetailWidthKey('a','p'))).toBe('640');
 width=1000;act(()=>observers.forEach(run=>run()));expect(separator()).toHaveAttribute('aria-valuenow','640');
 fireEvent.doubleClick(separator());expect(separator()).toHaveAttribute('aria-valuenow','420');
 expect(localStorage.getItem(graphDetailWidthKey('a','p'))).toBeNull();
});
test('expanding keeps graph and unsaved detail content mounted',()=>{
 const ui=render(view());const graph=ui.container.querySelector('.kw-graph-primary');
 const input=screen.getByLabelText('草稿');fireEvent.change(input,{target:{value:'未保存的理解'}});
 fireEvent.click(screen.getByRole('button',{name:'展开节点详情'}));
 expect(ui.container.querySelector('.kw-resizable-graph')).toHaveClass('kw-detail-expanded');
 expect(ui.container.querySelector('.kw-graph-primary')).toBe(graph);expect(screen.getByLabelText('草稿')).toBe(input);
 fireEvent.click(screen.getByRole('button',{name:'还原分栏'}));expect(input).toHaveValue('未保存的理解');
});
test('pointer drag grows the detail pane toward the left and saves at the end',()=>{
 render(view());
 const pointer=(name:string,x:number)=>fireEvent(separator(),Object.assign(new Event(name,{bubbles:true}),{pointerId:1,button:0,clientX:x}));
 pointer('pointerdown',700);pointer('pointermove',600);expect(separator()).toHaveAttribute('aria-valuenow','520');
 expect(localStorage.getItem(graphDetailWidthKey('a','p'))).toBeNull();
 pointer('pointerup',600);expect(localStorage.getItem(graphDetailWidthKey('a','p'))).toBe('520');
});
test('canvas height follows the actual top and stable observations do not repeat updates',()=>{
 const onHeight=vi.fn();render(view('p',onHeight));expect(onHeight).toHaveBeenLastCalledWith(484);
 const calls=onHeight.mock.calls.length;act(()=>observers.forEach(run=>run()));expect(onHeight).toHaveBeenCalledTimes(calls);
 Object.defineProperty(window,'innerHeight',{configurable:true,value:640});act(()=>window.dispatchEvent(new Event('resize')));
 expect(onHeight).toHaveBeenLastCalledWith(356);
});
test('a narrow container cannot accidentally latch expanded mode when it becomes wide again',()=>{
 width=600;const ui=render(view());expect(ui.container.querySelector('.kw-resizable-graph')).toHaveClass('kw-detail-expanded');
 fireEvent.click(screen.getByRole('button',{name:'还原分栏'}));
 width=1000;act(()=>observers.forEach(run=>run()));
 expect(ui.container.querySelector('.kw-resizable-graph')).not.toHaveClass('kw-detail-expanded');
 expect(screen.getByRole('button',{name:'展开节点详情'})).toBeEnabled();
});

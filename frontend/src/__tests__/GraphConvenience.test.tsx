import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
vi.mock('react-force-graph-2d',async()=>{const {forwardRef}=await import('react');return {default:forwardRef(({graphData}:any,_ref)=><div data-testid="graph-nodes">{graphData.nodes.map((n:any)=>n.uid).join(',')}</div>)}});
import Graph from '../pages/Graph';

test('search preserves a group of matching datasets and source context after selecting one',async()=>{
 const nodes=[{uid:'d1',name:'H2O',type:'dataset',is_match:true,access_links:[{url:'https://github.com/taeinkwon/h2odataset',label:'H2O 官方项目',origin:'name_match'}]},{uid:'d2',name:'TACO',type:'dataset',is_match:true},{uid:'p1',name:'Paper 1',type:'paper'},{uid:'m1',name:'Policy',type:'method'}];
 globalThis.fetch=vi.fn().mockImplementation(async(input:any)=>({ok:true,json:async()=>String(input).includes('/context')?{nodes,links:[{source:'p1',target:'d1',rel_type:'MENTIONS'}],matched_count:2,shown_matches:2,context_count:2}:String(input).includes('/neighbors')?{nodes:[nodes[0],nodes[2]],links:[{source:'p1',target:'d1',rel_type:'MENTIONS'}]}:{nodes:[],links:[]}}));
 render(<MemoryRouter><Graph/></MemoryRouter>);
 await screen.findByText('暂无可显示的图谱数据');
 const input=screen.getByLabelText('搜索图谱');
 fireEvent.change(input,{target:{value:'hand datasets'}});fireEvent.keyDown(input,{key:'Enter',code:'Enter',keyCode:13});
 await screen.findByText(/匹配 2 \/ 2 项/);
 expect(screen.getByTestId('graph-nodes').textContent).toContain('d2');
 fireEvent.click(screen.getByLabelText('H2O · 数据集'));
 expect((await screen.findByText('H2O 官方项目 ↗')).getAttribute('href')).toBe('https://github.com/taeinkwon/h2odataset');
 expect(screen.getByLabelText("H2O · 数据集").getAttribute("aria-pressed")).toBe("true");
 fireEvent.click(screen.getByText("继续展开相关节点").closest("button")!);
 await waitFor(()=>expect(screen.getByTestId('graph-nodes').textContent).toContain('d2'));
 fireEvent.click(screen.getByText("返回 / 收起上次展开").closest("button")!);
 expect(screen.getByLabelText("H2O · 数据集").getAttribute("aria-pressed")).toBe("true");
});

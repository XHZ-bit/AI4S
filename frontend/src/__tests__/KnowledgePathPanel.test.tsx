import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgePathPanel from '../components/knowledge/KnowledgePathPanel';
import {getKnowledgePath} from '../api/unifiedGraph';
import type {KnowledgeNode} from '../api/knowledge';
vi.mock('../api/unifiedGraph',()=>({getKnowledgePath:vi.fn()}));
vi.mock('antd',()=>({Alert:({message,description}:any)=><p role="alert">{message}{description}</p>,Button:({loading:_,children,...props}:any)=><button {...props}>{children}</button>,Space:({children}:any)=><div>{children}</div>,Select:({options,onChange,showSearch:_,optionFilterProp:__,...props}:any)=><select {...props} onChange={e=>onChange(e.target.value)}><option value="">请选择</option>{options.map((x:any)=><option key={x.value} value={x.value}>{x.label}</option>)}</select>}));
const nodes=['a','b'].map(id=>({id,label:'知识 '+id,metadata:{}} as KnowledgeNode));
beforeEach(()=>vi.mocked(getKnowledgePath).mockReset());
test('only queries on explicit request and never creates edges for missing paths',async()=>{
 const result=vi.fn();vi.mocked(getKnowledgePath).mockResolvedValue({nodes:[],edges:[],paths:[],cycle_detected:false,truncated:false,message:'没有已保存的连接。'});
 render(<KnowledgePathPanel projectId="p" nodes={nodes} currentNode="a" onNode={vi.fn()} onResult={result}/>);
 expect(getKnowledgePath).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('解释知识关系与学习路径'));
 fireEvent.change(screen.getByLabelText('路径终点'),{target:{value:'b'}});fireEvent.click(screen.getByText('查看路径'));
 await screen.findByText('没有已保存的连接。');
 expect(getKnowledgePath).toHaveBeenCalledWith('p','a','b','connection',expect.any(AbortSignal));expect(result).toHaveBeenCalledWith(undefined);
 expect(screen.queryByRole('list')).toBeNull();
});
test('prerequisite path exposes cycle warnings and navigates real nodes',async()=>{
 const onNode=vi.fn(),result=vi.fn();vi.mocked(getKnowledgePath).mockResolvedValue({nodes,edges:[{id:'e',source:'a',target:'b',origin:'inference',label:'前置',explanation:'系统推断'} as any],paths:[{node_ids:['a','b'],edge_ids:['e']}],cycle_detected:true,truncated:true,message:'已有前置关系'});
 render(<KnowledgePathPanel projectId="p" nodes={nodes} currentNode="a" onNode={onNode} onResult={result}/>);
 fireEvent.click(screen.getByText('解释知识关系与学习路径'));fireEvent.change(screen.getByLabelText('路径用途'),{target:{value:'prerequisites'}});fireEvent.click(screen.getByText('查看路径'));
 await screen.findByText(/存在循环依赖/);expect(getKnowledgePath).toHaveBeenCalledWith('p','a',undefined,'prerequisites',expect.any(AbortSignal));
 fireEvent.click(screen.getByRole('button',{name:'知识 b'}));expect(onNode).toHaveBeenCalledWith(nodes[1]);
 fireEvent.click(screen.getByText('退出路径视图'));await waitFor(()=>expect(result).toHaveBeenLastCalledWith(undefined));
});

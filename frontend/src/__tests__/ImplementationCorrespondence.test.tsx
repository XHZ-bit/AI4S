import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {vi} from 'vitest';
import ImplementationCorrespondence from '../components/knowledge/ImplementationCorrespondence';
import {getImplementations,patchImplementation} from '../api/knowledgeImplementations';
vi.mock('../api/knowledgeImplementations',()=>({getImplementations:vi.fn(),generateImplementations:vi.fn(),createImplementation:vi.fn(),patchImplementation:vi.fn()}));
const paper={id:'e1',source_id:'p',source_title:'论文',block_id:'b1',quote:'原文',locator:{page:2},source_version:'v1',origin:'source'};
const code={id:'e2',source_id:'c',source_title:'代码',block_id:'b2',quote:'x = 1',locator:{path:'a.py',start_line:8},source_version:'v2',origin:'source'};
const item={id:'m1',node_id:'n',paper_span:'原文',code_span:'x = 1',explanation:'实现对应',status:'confirmed' as const,implementation_kind:'source' as const,revision:3,paper_evidence:paper,code_evidence:code,stale:false,stale_reasons:[]};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(patchImplementation).mockResolvedValue({...item,status:'confirmed',revision:4});vi.mocked(getImplementations).mockResolvedValue({items:[item],code_sources:[],paper_evidence:[paper]});});
test('shows both sources, navigates to evidence and passes mapping into practice',async()=>{
 const onEvidence=vi.fn(),onPractice=vi.fn();render(<ImplementationCorrespondence projectId="p" nodeId="n" onEvidence={onEvidence} onPractice={onPractice}/>);
 fireEvent.click(screen.getByText('论文与代码对应'));
 expect(await screen.findByText('实现对应')).toBeTruthy();
 expect(screen.getByText(/a.py.*第 8 行.*版本 v2/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'查看代码来源'}));expect(onEvidence).toHaveBeenCalledWith(code);
 fireEvent.click(screen.getByRole('button',{name:'用于练习'}));expect(onPractice).toHaveBeenCalledWith('n','m1');
 fireEvent.click(screen.getByRole('button',{name:'否定对应'}));
 await waitFor(()=>expect(patchImplementation).toHaveBeenCalledWith('p','n','m1',{expected_revision:3,status:'rejected'}));
});
test('stale mapping cannot be confirmed without renewed review',async()=>{
 vi.mocked(getImplementations).mockResolvedValue({items:[{...item,stale:true,stale_reasons:['来源已更新']}],code_sources:[],paper_evidence:[paper]});
 render(<ImplementationCorrespondence projectId="p" nodeId="n" onEvidence={vi.fn()}/>);
 fireEvent.click(screen.getByText('论文与代码对应'));
 await screen.findByText('来源已更新');expect(screen.getByRole('button',{name:'确认对应'})).toBeDisabled();
});
test('limits unreviewed candidates while keeping reviewed items visible',async()=>{
 const proposed=Array.from({length:5},(_,i)=>({...item,id:`candidate-${i}`,status:'proposed' as const,explanation:`候选 ${i}`}));
 vi.mocked(getImplementations).mockResolvedValue({items:[...proposed,{...item,id:'confirmed',explanation:'已确认关系'}],code_sources:[],paper_evidence:[paper]});
 const {container}=render(<ImplementationCorrespondence projectId="p" nodeId="n" onEvidence={vi.fn()}/>);
 fireEvent.click(screen.getByText('论文与代码对应'));
 await screen.findByText('已确认关系');expect(screen.getByText('候选 0')).toBeTruthy();expect(screen.queryByText('候选 4')).toBeNull();
 expect(container.querySelector('[data-mapping-id="confirmed"]')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'显示其余 2 条候选'}));expect(screen.getByText('候选 4')).toBeTruthy();
});
test('editing preserves chosen evidence and confirms the saved revision',async()=>{
 const proposal={...item,status:'proposed' as const,code_source_id:'c',code_block_id:'b2'};
 vi.mocked(getImplementations).mockResolvedValue({items:[proposal],code_sources:[{id:'c',title:'代码',version:'v2',blocks:[{id:'b2',text:'x = 1',heading:'f',metadata:{start_line:8,end_line:8},ordinal:1}]}],paper_evidence:[paper]});
 vi.mocked(patchImplementation).mockResolvedValueOnce({...proposal,revision:4,explanation:'人工修订'}).mockResolvedValueOnce({...proposal,revision:5,status:'confirmed'});
 render(<ImplementationCorrespondence projectId="p" nodeId="n" onEvidence={vi.fn()}/>);
 fireEvent.click(screen.getByText('论文与代码对应'));await screen.findByText('实现对应');
 fireEvent.click(screen.getByRole('button',{name:/编\s*辑/}));
 fireEvent.change(screen.getByLabelText('对应说明'),{target:{value:'人工修订'}});
 fireEvent.click(screen.getByRole('button',{name:/保\s*存/}));
 await screen.findByText('人工修订');
 expect(patchImplementation).toHaveBeenCalledWith('p','n','m1',expect.objectContaining({expected_revision:3,paper_evidence_id:'e1',code_source_id:'c',code_block_id:'b2',explanation:'人工修订'}));
 fireEvent.click(screen.getByRole('button',{name:'确认对应'}));
 await waitFor(()=>expect(patchImplementation).toHaveBeenCalledWith('p','n','m1',{expected_revision:4,status:'confirmed'}));
});

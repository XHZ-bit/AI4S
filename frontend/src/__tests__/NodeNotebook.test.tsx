import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import NodeNotebook from '../components/knowledge/NodeNotebook';
import type {KnowledgeNode} from '../api/knowledge';

const api=vi.hoisted(()=>({list:vi.fn(),save:vi.fn(),catalog:vi.fn(),preview:vi.fn(),download:vi.fn()}));
vi.mock('../api/knowledgeOutcomes',()=>({listNodeNotes:api.list,saveNodeNote:api.save,getNodeOutcomes:api.catalog,previewNodeOutcomes:api.preview,noteContext:(item:any)=>JSON.parse(item?.source_json||'{}')}));
vi.mock('../components/workbench/Notebook',()=>({download:api.download}));
vi.mock('../components/SessionContext',()=>({useCurrentAccount:()=>({id:'learner'})}));
const node:KnowledgeNode={id:'n',project_id:'p',source_id:'s',label:'Gate',version:1,kind:'concept',metadata:{},evidence_ids:[],summary:'A gate',origin:'source',parent_id:null,research_status:'unspecified',hidden:false,source_missing:false};
const saved={id:'note',version:1,title:'Gate · 我的理解',body:'Saved understanding',kind:'note',project_id:'p',source_json:JSON.stringify({knowledge_node_id:'n',source_id:'s',node_version:1,source_version:'v1'})};
beforeEach(()=>{vi.clearAllMocks();localStorage.clear();api.list.mockResolvedValue({items:[]});api.save.mockImplementation(async value=>({...value,version:value.version+1,source_json:JSON.stringify({knowledge_node_id:'n',source_id:'s',node_version:1,source_version:'v1',unresolved_questions:value.unresolved_questions})}));api.catalog.mockResolvedValue({notes:[saved],evidence:[{id:'e',source_title:'Paper A',locator:{page:3}}],lessons:[],practices:[],comparisons:[]});api.preview.mockResolvedValue({filename:'note.md',markdown:'# Selected understanding',selected_count:1})});

test('node notes save explicit understanding and questions without reading export or generation',async()=>{
 render(<NodeNotebook projectId="p" node={node}/>);
 const field=await screen.findByLabelText('我的理解');await waitFor(()=>expect(field).toBeEnabled());
 fireEvent.change(field,{target:{value:'The gate scales the residual.'}});
 fireEvent.click(screen.getByText('未解决的问题',{selector:'summary'}));fireEvent.change(screen.getByLabelText('未解决的问题'),{target:{value:'How is its range bounded?'}});
 expect(api.save).not.toHaveBeenCalled();expect(api.catalog).not.toHaveBeenCalled();expect(api.preview).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'保存笔记'}));await screen.findByText('已保存');
 expect(api.save).toHaveBeenCalledWith(expect.objectContaining({project_id:'p',knowledge_node_id:'n',body:'The gate scales the residual.',unresolved_questions:'How is its range bounded?'}));
 expect(localStorage.getItem('paperstride:node-note:learner:p:n')).toBeNull();
});

test('conflicts keep the draft and require an explicit choice before another save',async()=>{
 api.list.mockResolvedValueOnce({items:[saved]}).mockResolvedValue({items:[{...saved,version:2,body:'Changed elsewhere'}]});api.save.mockRejectedValueOnce(Object.assign(new Error('conflict'),{status:409}));
 render(<NodeNotebook projectId="p" node={node}/>);await screen.findByDisplayValue('Saved understanding');fireEvent.change(screen.getByLabelText('我的理解'),{target:{value:'My unsaved reasoning'}});fireEvent.click(screen.getByRole('button',{name:'保存笔记'}));
 await screen.findByText('笔记或来源已有更新。你的草稿已保留，请比较后保存。');expect(screen.getByLabelText('我的理解')).toHaveValue('My unsaved reasoning');expect(api.save).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole('button',{name:'保留我的草稿'}));fireEvent.click(screen.getByRole('button',{name:'保存笔记'}));await screen.findByText('已保存');expect(api.save).toHaveBeenLastCalledWith(expect.objectContaining({version:2,body:'My unsaved reasoning'}));
});

test('node-scoped browser drafts restore and late responses cannot replace another node',async()=>{
 let resolveOld!:(value:unknown)=>void;api.list.mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve})).mockResolvedValue({items:[]});
 const {rerender}=render(<NodeNotebook projectId="p" node={node}/>);rerender(<NodeNotebook projectId="p" node={{...node,id:'new'}}/>);
 await waitFor(()=>expect(screen.getByLabelText('我的理解')).toBeEnabled());fireEvent.change(screen.getByLabelText('我的理解'),{target:{value:'New-node draft'}});
 await act(async()=>resolveOld({items:[saved]}));expect(screen.getByLabelText('我的理解')).toHaveValue('New-node draft');
 await waitFor(()=>expect(localStorage.getItem('paperstride:node-note:learner:p:new')).toContain('New-node draft'));
});

test('export starts empty and downloads only an explicitly previewed saved selection',async()=>{
 render(<NodeNotebook projectId="p" node={node}/>);await waitFor(()=>expect(screen.getByLabelText('我的理解')).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'导出学习成果'}));await screen.findByText('选择要带走的内容：');
 expect(screen.getByLabelText('选择学习成果导出内容')).toBeVisible();
 expect(screen.getByRole('button',{name:'预览所选内容'})).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox',{name:'Gate · 我的理解'}));fireEvent.click(screen.getByRole('button',{name:'预览所选内容'}));await screen.findByLabelText('学习成果导出预览');
 expect(api.preview).toHaveBeenCalledWith('p','n',{note_ids:['note'],evidence_ids:[],learning_sections:[],practice_ids:[],comparison_cells:[],mappings:[]});
 fireEvent.click(screen.getByRole('button',{name:'下载 Markdown'}));expect(api.download).toHaveBeenCalledWith('note.md','# Selected understanding','text/markdown;charset=utf-8');
});

test('an explicitly selected AI answer is appended to a draft and is not silently saved',async()=>{
 api.list.mockResolvedValue({items:[saved]});render(<NodeNotebook projectId="p" node={node} initialDraft={{text:'Model explanation',origin:'saved_ai_answer',nonce:'1'}}/>);
 await waitFor(()=>expect((screen.getByLabelText('我的理解') as HTMLTextAreaElement).value).toContain('Model explanation'));
 expect((screen.getByLabelText('我的理解') as HTMLTextAreaElement).value).toContain('Saved understanding');expect(api.save).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'保存笔记'}));await screen.findByText('已保存');expect(api.save).toHaveBeenCalledWith(expect.objectContaining({content_origin:'saved_ai_answer'}));
});

test('answer citations remain structured, can reopen, and accompany the saved note',async()=>{
 const reference={id:'evidence-1',source_id:'s',source_title:'Attention paper',block_id:'formula-1',source_version:'arxiv-v7',origin:'source',quote:'Divide by the square root.',locator:{page:4}};
 const open=vi.fn(),savedEvent=vi.fn();window.addEventListener('paperstride:note-saved',savedEvent);
 try{
  render(<NodeNotebook projectId="p" node={node} onEvidence={open} initialDraft={{text:'My check',origin:'saved_ai_answer',evidence:[reference]}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Attention paper · 第 4 页'}));
  expect(open).toHaveBeenCalledWith(reference);
  expect(api.save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'保存笔记'}));await screen.findByText('已保存');
  expect(api.save).toHaveBeenCalledWith(expect.objectContaining({evidence_references:[reference]}));
  expect(savedEvent).toHaveBeenCalledOnce();
  expect(savedEvent.mock.calls[0][0].detail).toEqual(expect.objectContaining({projectId:'p',nodeId:'n',sourceId:'s'}));
 }finally{window.removeEventListener('paperstride:note-saved',savedEvent)}
});

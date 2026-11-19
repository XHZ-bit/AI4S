import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import NodeMaterials from '../components/knowledge/NodeMaterials';
import NodeCreate from '../components/knowledge/NodeCreate';
import NodeNoteSummary from '../components/knowledge/NodeNoteSummary';
import * as materials from '../api/knowledgeMaterials';
import {listNodeNotes,type KnowledgeNote} from '../api/knowledgeOutcomes';
import type {KnowledgeNode,KnowledgeSource} from '../api/knowledge';
vi.mock('../api/knowledgeMaterials',()=>({getNodeMaterials:vi.fn(),bindNodeMaterial:vi.fn(),uploadNodeMaterial:vi.fn(),updateNodeMaterial:vi.fn(),createManualNode:vi.fn()}));
vi.mock('../api/knowledgeOutcomes',async()=>({...await vi.importActual<typeof import('../api/knowledgeOutcomes')>('../api/knowledgeOutcomes'),listNodeNotes:vi.fn()}));
const source={id:'s',project_id:'p',title:'教学资料',version:'v1',filename:'notes.md',kind:'report',media_type:'text/markdown',removed:false} as KnowledgeSource;
const item:materials.NodeMaterial={id:'m',project_id:'p',node_id:'n',source_id:'s',revision:1,note:'用来核对输入条件',removed:false,created_at:'today',updated_at:'today',reviewed_by:'用户',source_snapshot:source,current_source:source,source_changed:false,source_missing:false,original_url:'/api/projects/p/sources/s/file'};
const props={projectId:'p',nodeId:'n',sources:[source],onRead:vi.fn(),onUpdated:vi.fn()};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(materials.getNodeMaterials).mockResolvedValue({items:[]});vi.mocked(listNodeNotes).mockResolvedValue({items:[]});});

test('existing project material can be attached and reopened at its actual source',async()=>{
 vi.mocked(materials.bindNodeMaterial).mockResolvedValue({item});
 render(<NodeMaterials {...props}/>);
 fireEvent.click(screen.getByRole('button',{name:'添加资料'}));
 fireEvent.change(screen.getByLabelText('节点资料说明'),{target:{value:item.note}});
 fireEvent.change(screen.getByRole('combobox',{name:'关联已有课题资料'}),{target:{value:source.id}});
 fireEvent.click(screen.getByRole('button',{name:'关联所选资料'}));
 await waitFor(()=>expect(materials.bindNodeMaterial).toHaveBeenCalledWith('p','n','s',item.note));
 fireEvent.click(await screen.findByRole('button',{name:'查看资料'}));expect(props.onRead).toHaveBeenCalledWith('s');
 expect(materials.uploadNodeMaterial).not.toHaveBeenCalled();
});

test('an uploaded file is explicitly attached with the current node and note',async()=>{
 vi.mocked(materials.uploadNodeMaterial).mockResolvedValue({item,source});
 render(<NodeMaterials {...props}/>);fireEvent.click(screen.getByRole('button',{name:'添加资料'}));
 const file=new File(['# 教学笔记\n自己记录的条件。'],'personal.md',{type:'text/markdown'});
 fireEvent.change(screen.getByLabelText('上传节点资料'),{target:{files:[file]}});
 fireEvent.change(screen.getByLabelText('节点资料说明'),{target:{value:'核对记录'}});
 fireEvent.click(screen.getByRole('button',{name:'导入并关联'}));
 await waitFor(()=>expect(materials.uploadNodeMaterial).toHaveBeenCalledWith('p','n',file,'核对记录'));
 expect(await screen.findByText('资料已导入并保存到当前节点')).toBeVisible();
});

test('source removal preserves the attachment note while unlinking removes only its association',async()=>{
 vi.mocked(materials.getNodeMaterials).mockResolvedValue({items:[{...item,source_missing:true,current_source:null}]});
 vi.mocked(materials.updateNodeMaterial).mockResolvedValue({item:{...item,removed:true,revision:2}});
 render(<NodeMaterials {...props}/>);
 expect(await screen.findByText(item.note)).toBeVisible();
 expect(screen.getByRole('button',{name:'查看资料'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'移除关联'}));
 await waitFor(()=>expect(materials.updateNodeMaterial).toHaveBeenCalledWith('p','n','m',{expected_revision:1,removed:true}));
 expect(await screen.findByText('已移除关联，课题中的原资料仍保留')).toBeVisible();
});

test('failed binding after upload retains a recovery path to the saved source',async()=>{
 vi.mocked(materials.uploadNodeMaterial).mockRejectedValue(Object.assign(new Error('conflict'),{status:409,savedSource:source}));
 render(<NodeMaterials {...props}/>);fireEvent.click(screen.getByRole('button',{name:'添加资料'}));
 fireEvent.change(screen.getByLabelText('上传节点资料'),{target:{files:[new File(['note'],'note.md')]}});
 fireEvent.change(screen.getByLabelText('节点资料说明'),{target:{value:'保留的说明'}});
 fireEvent.click(screen.getByRole('button',{name:'导入并关联'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('资料已保存在课题中');
 expect(screen.getByLabelText('节点资料说明')).toHaveValue('保留的说明');expect(props.onUpdated).toHaveBeenCalled();
});

test('manual creation is explicit, scoped, and retains input when persistence fails',async()=>{
 vi.mocked(materials.createManualNode).mockRejectedValue(new Error('offline'));
 render(<NodeCreate projectId="p" onCreated={vi.fn()} onCancel={vi.fn()}/>);
 expect(materials.createManualNode).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('新节点名称'),{target:{value:'待验证假设'}});
 fireEvent.change(screen.getByLabelText('新节点说明'),{target:{value:'先记录自己的研究想法。'}});
 fireEvent.click(screen.getByRole('button',{name:'保存节点'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('输入已保留');
 expect(materials.createManualNode).toHaveBeenCalledWith('p',{label:'待验证假设',summary:'先记录自己的研究想法。',kind:'concept'});
 expect(screen.getByLabelText('新节点名称')).toHaveValue('待验证假设');
});

test('a saved node note is immediately visible when reopening its node',async()=>{
 vi.mocked(listNodeNotes).mockResolvedValue({items:[{id:'note',kind:'note',body:'我的研究记录：先检查分组条件。',context:{content_origin:'user'}} as KnowledgeNote]});
 const onEdit=vi.fn();render(<NodeNoteSummary projectId="p" nodeId="n" onEdit={onEdit}/>);
 expect(await screen.findByText('我的研究记录：先检查分组条件。')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'编辑笔记'}));expect(onEdit).toHaveBeenCalled();
});

test('a late note read cannot overwrite a newer saved event or leak to another node',async()=>{
 let resolve!:(value:{items:KnowledgeNote[]})=>void;
 vi.mocked(listNodeNotes).mockImplementation((_p,node)=>node==='old'?new Promise(r=>{resolve=r}):Promise.resolve({items:[]}));
 const view=render(<NodeNoteSummary projectId="p" nodeId="old" onEdit={vi.fn()}/>);
 await waitFor(()=>expect(listNodeNotes).toHaveBeenCalled());
 act(()=>window.dispatchEvent(new CustomEvent('paperstride:note-saved',{detail:{projectId:'p',nodeId:'old',body:'刚保存的新笔记',contentOrigin:'user'}})));
 expect(await screen.findByText('刚保存的新笔记')).toBeVisible();
 await act(async()=>resolve({items:[{id:'note',kind:'note',body:'旧笔记'} as KnowledgeNote]}));
 expect(screen.queryByText('旧笔记')).toBeNull();
 view.rerender(<NodeNoteSummary projectId="p" nodeId="new" onEdit={vi.fn()}/>);
 await screen.findByRole('button',{name:'记录文字'});expect(screen.queryByText('刚保存的新笔记')).toBeNull();
});

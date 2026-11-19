import {act,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeSources from '../components/knowledge/KnowledgeSources';
import type {KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({upload:vi.fn(),analyze:vi.fn()}));
vi.mock('../api/knowledge',async()=>({...await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge'),uploadKnowledgeSource:api.upload,analyzeKnowledgeSource:api.analyze}));
vi.mock('../api/client',()=>({apiGet:vi.fn(async()=>[])}));
vi.mock('../components/workbench/ProjectWorkbench',()=>({default:()=> <input aria-label="研究记录草稿"/>}));
vi.mock('../components/knowledge/SourceCoverage',()=>({default:()=>null}));
vi.mock('../components/workspace/PdfReader',()=>({default:()=>null}));
vi.mock('antd',()=>{
 const Space=Object.assign(({children}:any)=><div>{children}</div>,{Compact:({children}:any)=><div>{children}</div>});
 const Input=Object.assign(({autoSize:_,...props}:any)=><input {...props}/>,{TextArea:({autoSize:_,...props}:any)=><textarea {...props}/>});
 return {Space,Input,Button:({children,type:_,loading:__,size:___,...props}:any)=><button {...props}>{children}</button>,Select:({options,onChange,showSearch:_,optionFilterProp:__,...props}:any)=><select {...props} onChange={event=>onChange?.(event.target.value)}>{options?.map((item:any)=><option key={item.value} value={item.value}>{item.label}</option>)}</select>,Alert:({message,description}:any)=><div role="alert">{message}{description}</div>,Spin:()=>null,Tag:({children}:any)=><span>{children}</span>};
});
const source:KnowledgeSource={id:'s',project_id:'p',asset_id:'a',version:'v1',title:'Saved source',filename:'paper.md',kind:'report',media_type:'text/markdown',removed:false,created_at:'2026-11-12'};
beforeEach(()=>vi.clearAllMocks());
async function show(sources=[source]){await act(async()=>{render(<MemoryRouter><KnowledgeSources projectId="p" sources={sources} onUpdated={vi.fn()} onRead={vi.fn()} onGraph={vi.fn()}/></MemoryRouter>)});}

test('existing sources lead while the import panel retains its unfinished link',async()=>{
 await show();const link=screen.getByLabelText('资料链接');expect(link).not.toBeVisible();expect(screen.getByRole('button',{name:'打开资料'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'添加资料'}));expect(link).toBeVisible();fireEvent.change(link,{target:{value:'https://example.org/unfinished-paper'}});
 fireEvent.click(screen.getByRole('button',{name:'收起导入'}));expect(link).not.toBeVisible();fireEvent.click(screen.getByRole('button',{name:'添加资料'}));expect(link).toHaveValue('https://example.org/unfinished-paper');
 expect(api.upload).not.toHaveBeenCalled();expect(api.analyze).not.toHaveBeenCalled();
});
test('an empty space presents import controls immediately',async()=>{
 await show([]);expect(screen.getByLabelText('资料链接')).toBeVisible();expect(screen.getByRole('button',{name:'选择文件并分析'})).toBeVisible();expect(screen.getByRole('button',{name:'收起导入'})).toHaveAttribute('aria-expanded','true');
});
test('records have a direct keyboard entry and stay mounted when switching sources',async()=>{
 await show();const record=screen.getByLabelText('研究记录草稿');expect(record).not.toBeVisible();fireEvent.keyDown(screen.getByRole('tab',{name:'资料'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'研究记录'})).toHaveFocus();expect(record).toBeVisible();fireEvent.change(record,{target:{value:'未完成的研究判断'}});
 fireEvent.click(screen.getByRole('tab',{name:'资料'}));expect(record).not.toBeVisible();fireEvent.click(screen.getByRole('tab',{name:'研究记录'}));expect(screen.getByLabelText('研究记录草稿')).toBe(record);expect(record).toHaveValue('未完成的研究判断');
 fireEvent.click(screen.getByRole('button',{name:'添加资料'}));expect(screen.getByLabelText('资料链接')).toBeVisible();expect(screen.getByRole('tab',{name:'资料'})).toHaveAttribute('aria-selected','true');
});

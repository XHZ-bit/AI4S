import {beforeEach,expect,test,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
const canvas=vi.hoisted(()=>({props:null as any}));
vi.mock('react-force-graph-2d',async()=>{const {forwardRef}=await import('react');return {default:forwardRef((props:any,_ref)=>{canvas.props=props;return <div data-testid="graph-nodes">{props.graphData.nodes.map((n:any)=>n.uid).join(',')}</div>})}});
import Graph from '../pages/Graph';

const library={id:'library',kind:'library',project_id:null,title:'资料库'};
const project={id:'space-a',kind:'project',project_id:'space-a',title:'空间 A'};
const root=(id:string,scope:any)=>({id,project_id:scope.id,source_id:'source-'+id,kind:'paper',label:'Shared paper',parent_id:null,paper_uid:'paper-uid',source_title:'Shared paper',scope,metadata:{source_root:true,child_count:61},evidence_ids:[]});
const roots=[root('library-root',library),root('space-root',project)];
const legacy={...roots[0],id:'historical-record',parent_id:'library-root',metadata:{legacy_id:27,legacy_passage_id:'passage-27'},label:'Shared paper'};
const display=(n:any)=>({...n,uid:n.id,name:n.label,type:n.kind});
const method=display({...roots[0],id:'method',kind:'method',label:'Readable method',parent_id:'library-root',metadata:{}});
beforeEach(()=>{
 globalThis.fetch=vi.fn().mockImplementation(async(input:any)=>{
  const url=new URL(String(input),'http://localhost');
  let value:any={nodes:[],links:[]};
  if(url.pathname==='/api/knowledge/graph')value={nodes:url.searchParams.has('overview')?roots.filter(n=>!url.searchParams.has('project_id')||n.scope.id===url.searchParams.get('project_id')):[],edges:[],scopes:[library,project],overview:true,truncated:false};
  if(url.pathname.startsWith('/api/graph/neighbors/'))value={nodes:[display(roots[0]),method],links:[{source:'library-root',target:'method',rel_type:'MENTIONS'}],truncated:true};
  if(url.pathname==='/api/graph/context')value={nodes:[display(legacy)],links:[],matched_count:1,shown_matches:1,context_count:0};
  return {ok:true,json:async()=>value};
 });
});

test('global overview displays distinct scoped sources and expands the chosen source with a bounded request',async()=>{
 render(<MemoryRouter><Graph/></MemoryRouter>);
 const source=await screen.findByLabelText('Shared paper · 论文 · 资料库');
 expect(screen.getByLabelText('Shared paper · 论文 · 空间 A')).toBeVisible();
 expect(within(source).getByText('论文 · 资料库 · 61 条知识')).toBeVisible();
 expect(screen.getByTestId('graph-nodes')).toHaveTextContent('library-root,space-root');
 fireEvent.click(source);
 expect(await screen.findByLabelText('Readable method · 方法 · 资料库')).toBeVisible();
 expect(screen.getByTestId('graph-nodes')).not.toHaveTextContent('space-root');
 const calls=vi.mocked(globalThis.fetch).mock.calls.map(([url])=>String(url));
 expect(calls.some(url=>url.includes('/neighbors/library-root?')&&url.includes('project_id=library')&&url.includes('limit=50'))).toBe(true);
 expect(calls.some(url=>url.includes('/api/graph/overview'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'返回 / 收起上次展开'}));
 expect(screen.getByRole('heading',{name:'来源总览'})).toBeVisible();
 expect(screen.getByLabelText('Shared paper · 论文 · 空间 A')).toBeVisible();
});

test('library source reading keeps graph return context without impersonating a research project',async()=>{
 render(<MemoryRouter initialEntries={['/graph?project_id=library&project=library']}><Graph/></MemoryRouter>);
 fireEvent.click(await screen.findByLabelText('Shared paper · 论文 · 资料库'));
 const link=await screen.findByRole('link',{name:'阅读这篇论文'});
 const url=new URL(link.getAttribute('href')!,'http://localhost');
 expect(url.pathname).toBe('/papers/paper-uid');
 expect(url.searchParams.has('project')).toBe(false);
 expect(url.searchParams.get('returnTo')).toContain('/graph?');
 expect(url.searchParams.get('returnTo')).toContain('project_id=library');
});

test('historical paper records remain searchable and their link explicitly opens source evidence',async()=>{
 render(<MemoryRouter initialEntries={['/graph?project_id=library']}><Graph/></MemoryRouter>);
 await screen.findByLabelText('Shared paper · 论文 · 资料库');
 const input=screen.getByLabelText('搜索图谱');
 fireEvent.change(input,{target:{value:'Shared paper'}});fireEvent.keyDown(input,{key:'Enter',code:'Enter',keyCode:13});
 await screen.findByText(/匹配 1 \/ 1 项/);
 fireEvent.click(screen.getByLabelText('Shared paper · 论文 · 资料库'));
 expect(await screen.findByText(/历史知识记录 #27/)).toBeVisible();
 const link=screen.getByRole('link',{name:'查看来源原文'});
 const url=new URL(link.getAttribute('href')!,'http://localhost');
 expect(url.searchParams.get('ref')).toBe('passage:passage-27');
 expect(url.searchParams.has('project')).toBe(false);
 expect(screen.queryByRole('link',{name:'阅读这篇论文'})).toBeNull();
 expect(vi.mocked(globalThis.fetch).mock.calls.some(([url])=>String(url).includes('/neighbors/historical-record'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:/重\s*置/}));
 await waitFor(()=>expect(screen.getByTestId('graph-nodes')).toHaveTextContent('library-root'));
});

test('library relationship evidence links to its actual source and clears stale project context',async()=>{
 const base=globalThis.fetch;
 const other=display({...roots[0],id:'other-root',source_id:'other-source',paper_uid:'other-paper',label:'Other source'});
 const edge={id:'edge',source:'library-root',target:'other-root',rel_type:'MENTIONS',evidence_ids:['evidence']};
 globalThis.fetch=vi.fn().mockImplementation(async(input:any,...args:any[])=>{
  const url=String(input);
  if(url.includes('/neighbors/'))return {ok:true,json:async()=>({nodes:[display(roots[0]),other],links:[edge]})};
  if(url.includes('/api/knowledge/edges/'))return {ok:true,json:async()=>({edge:{label:'Actual relation',explanation:'Saved source evidence'},scope:library,evidence:[{id:'evidence',source_id:'other-source',source_title:'Other source',quote:'Actual evidence',locator:{page:3}},{id:'missing',source_id:'absent-source',source_title:'Unresolved source',quote:'Unavailable location',locator:{}}]})};
  return base(input,...args);
 });
 render(<MemoryRouter initialEntries={['/graph?project_id=library&project=library']}><Graph/></MemoryRouter>);
 fireEvent.click(await screen.findByLabelText('Shared paper · 论文 · 资料库'));
 fireEvent.click(await screen.findByText('Shared paper → 提及 → Other source'));
 fireEvent.click(screen.getByRole('button',{name:/查看来源 1/}));
 const link=await screen.findByRole('link',{name:'打开原文位置'});
 const url=new URL(link.getAttribute('href')!,'http://localhost');
 expect(url.pathname).toBe('/papers/other-paper');
 expect(url.searchParams.get('page')).toBe('3');
 expect(url.searchParams.has('project')).toBe(false);
 expect(screen.getAllByRole('link',{name:'打开原文位置'})).toHaveLength(1);
});

test('a project report without a paper ID opens its source and never creates a false paper link',async()=>{
 const report={...roots[1],id:'report-root',source_id:'report-source',paper_uid:null,kind:'report',label:'Project report'};
 globalThis.fetch=vi.fn().mockImplementation(async(input:any)=>({ok:true,json:async()=>String(input).includes('/neighbors/')?{nodes:[{...display(report),sources:[{paper_uid:null,paper_title:'Project report',source_id:'report-source',project_id:'space-a'}]}],links:[]}:{nodes:[report],edges:[],scopes:[project],overview:true}}));
 render(<MemoryRouter initialEntries={['/graph?project_id=space-a']}><Graph/></MemoryRouter>);
 fireEvent.click(await screen.findByRole('button',{name:/^Project report ·/}));
 const link=await screen.findByRole('link',{name:'查看来源原文'});
 const url=new URL(link.getAttribute('href')!,'http://localhost');
 expect(url.pathname).toBe('/research/space-a');
 expect(url.searchParams.get('view')).toBe('reading');
 expect(url.searchParams.get('source')).toBe('report-source');
 expect(screen.queryByRole('heading',{name:'来源论文'})).toBeNull();
 expect(screen.getAllByRole('link').every(a=>!a.getAttribute('href')?.match(/\/papers\/(?:null|undefined)/))).toBe(true);
 const context={beginPath:vi.fn(),arc:vi.fn(),stroke:vi.fn(),fill:vi.fn(),measureText:()=>({width:40}),fillText:vi.fn()};
 canvas.props.nodeCanvasObject({...display(report),x:0,y:0},context,1);
 expect(context.fillText).toHaveBeenCalledWith('Project report',0,7);
});

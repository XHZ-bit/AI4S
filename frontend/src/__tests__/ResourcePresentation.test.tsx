import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import ResourceExplorer from '../components/knowledge/ResourceExplorer';
import {addNodeResource,getNodeResources,type KnowledgeResource} from '../api/knowledgeExperience';
import type {KnowledgeEvidence} from '../api/knowledge';

vi.mock('../api/knowledgeExperience',()=>({getNodeResources:vi.fn(),addNodeResource:vi.fn()}));
const search:KnowledgeResource={id:'search',title:'在哔哩哔哩搜索相关讲解',url:'https://search.bilibili.com/all?keyword=attention',type:'search',origin:'search',reason:'站外搜索入口；不是已经核验的具体资源',access_status:'not_checked'};
const tutorial:KnowledgeResource={id:'t',title:'注意力入门课程',url:'https://example.org/attention',type:'tutorial',origin:'user',fetched:false,access_status:'not_checked',reason:'用示意图说明输入与输出'};
const video:KnowledgeResource={id:'v',title:'点积视频',url:'https://www.youtube.com/watch?v=aircAruvnKk',type:'video',origin:'catalog',access_status:'source_verified'};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(getNodeResources).mockResolvedValue({items:[]});});
function open(){fireEvent.click(screen.getByText(/^学习资料/,{selector:'summary'}));}

test('search shortcuts are useful actions without being counted or represented as retrieved resources',async()=>{
 vi.mocked(getNodeResources).mockResolvedValue({items:[search,{...search,id:'youtube',url:'https://www.youtube.com/results?search_query=attention'},{...search,id:'papers',url:'https://scholar.google.com/scholar?q=attention'}]});
 render(<ResourceExplorer projectId="p" nodeId="n"/>);open();
 const shortcuts=await screen.findByRole('navigation',{name:'站外搜索'});
 expect(within(shortcuts).getAllByRole('link')).toHaveLength(3);
 expect(within(shortcuts).getByRole('link',{name:'哔哩哔哩'})).toHaveAttribute('href',search.url);
 expect(screen.getByText('学习资料',{selector:'summary'})).toBeVisible();
 expect(screen.queryByRole('list',{name:'已保存学习资料'})).not.toBeInTheDocument();
 expect(screen.queryByText(/并非已经找到|不是已经核验|尚未检测访问/)).toBeNull();
 expect(screen.queryByLabelText('筛选学习资料类型')).toBeNull();
});

test('filters and counts apply to concrete resources while search remains available and metadata is opt-in',async()=>{
 vi.mocked(getNodeResources).mockResolvedValue({items:[tutorial,video,search]});
 render(<ResourceExplorer projectId="p" nodeId="n"/>);open();
 await screen.findByRole('link',{name:tutorial.title});
 expect(screen.getByText('学习资料 · 2',{selector:'summary'})).toBeVisible();
 const row=screen.getByRole('link',{name:tutorial.title}).closest('li')!;
 expect(within(row).getByText('未检测')).not.toBeVisible();
 expect(within(row).queryByText(/已核实|已读取来源内容/)).toBeNull();
 fireEvent.click(within(row).getByText('资源详情',{selector:'summary'}));
 expect(within(row).getByText('未检测')).toBeVisible();
 expect(within(row).getByText('你添加的链接')).toBeVisible();
 expect(within(row).getByText('资源链接')).toBeVisible();
 expect(getNodeResources).toHaveBeenCalledTimes(1);
 fireEvent.change(screen.getByLabelText('筛选学习资料类型'),{target:{value:'video'}});
 expect(screen.queryByRole('link',{name:tutorial.title})).toBeNull();
 expect(screen.getByRole('link',{name:video.title})).toBeVisible();
 expect(screen.getByRole('navigation',{name:'站外搜索'})).toBeVisible();
});

test('legacy search URLs are separated and saved evidence metadata survives a resource-service failure',async()=>{
 const evidence={id:'e',source_id:'s',source_title:'原图',block_id:'b',quote:'图注',locator:{page:2},source_version:'v1',origin:'source'} as KnowledgeEvidence;
 vi.mocked(getNodeResources).mockRejectedValue(new Error('temporary failure'));
 const onEvidence=vi.fn();
 render(<ResourceExplorer projectId="p" nodeId="n" onEvidence={onEvidence} initialItems={[
  {title:'旧搜索入口',url:search.url,type:'tutorial'},
  {title:'已保存原图',url:'/api/projects/p/sources/s/images/b',type:'image',origin:'source',access_status:'local',checked_at:'2026-11-17',fetched:true,evidence},
 ]}/>);open();
 expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法更新');
 expect(screen.getByText('学习资料 · 1',{selector:'summary'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'定位原文'}));expect(onEvidence).toHaveBeenCalledWith(evidence);
 fireEvent.click(screen.getByText('资源详情',{selector:'summary'}));
 expect(screen.getByText('2026-11-17')).toBeVisible();
 expect(screen.getByRole('navigation',{name:'站外搜索'})).toBeVisible();
});

test('a failed link keeps a visible recovery action without treating unchecked links as broken',async()=>{
 vi.mocked(getNodeResources).mockResolvedValue({items:[tutorial,{...video,access_status:'unavailable'}]});
 render(<ResourceExplorer projectId="p" nodeId="n"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'添加替代链接'}));
 expect(screen.getByLabelText('资源标题')).toHaveValue(video.title);
 expect(screen.getByLabelText('资源地址')).toHaveValue('');
 expect(screen.getAllByText('这个链接最近一次访问未成功。')).toHaveLength(1);
 expect(screen.getByRole('link',{name:video.title})).toHaveAttribute('href',video.url);
});

test('a late read from the previous node cannot overwrite the current resource list',async()=>{
 let resolve!:(value:{items:KnowledgeResource[]})=>void;
 vi.mocked(getNodeResources).mockImplementation((_p,node)=>node==='old'?new Promise(r=>{resolve=r}):Promise.resolve({items:[video]}));
 const mounted=render(<ResourceExplorer projectId="p" nodeId="old"/>);open();
 await waitFor(()=>expect(getNodeResources).toHaveBeenCalled());
 mounted.rerender(<ResourceExplorer projectId="p" nodeId="new"/>);
 await screen.findByRole('link',{name:video.title});
 await act(async()=>{resolve({items:[tutorial]})});
 expect(screen.queryByRole('link',{name:tutorial.title})).toBeNull();
 expect(screen.getByRole('link',{name:video.title})).toBeVisible();
});

test('an addition completing after navigation cannot inject the old resource into a new node',async()=>{
 let resolve!:(value:KnowledgeResource)=>void;
 vi.mocked(addNodeResource).mockImplementation(()=>new Promise(r=>{resolve=r}));
 const mounted=render(<ResourceExplorer projectId="p" nodeId="old"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'添加资源链接'}));
 fireEvent.change(screen.getByLabelText('资源标题'),{target:{value:tutorial.title}});
 fireEvent.change(screen.getByLabelText('资源地址'),{target:{value:tutorial.url}});
 fireEvent.click(screen.getByRole('button',{name:'保存到当前空间'}));
 await waitFor(()=>expect(addNodeResource).toHaveBeenCalledOnce());
 mounted.rerender(<ResourceExplorer projectId="p" nodeId="new"/>);
 await act(async()=>{resolve(tutorial)});
 expect(screen.queryByRole('link',{name:tutorial.title})).toBeNull();
 expect(screen.queryByText('链接已保存')).toBeNull();
});

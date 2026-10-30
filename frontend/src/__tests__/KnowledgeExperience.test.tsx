import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import ResourceExplorer,{safeKnowledgeUrl,videoEmbed} from '../components/knowledge/ResourceExplorer';
import LearningProgress from '../components/knowledge/LearningProgress';
import LearningPath from '../components/knowledge/LearningPath';
import NodeQuestion from '../components/knowledge/NodeQuestion';
import KnowledgeText,{safeRichUrl} from '../components/knowledge/KnowledgeText';
import PracticeVisuals,{parsePracticeOutput,validatePracticeVisual,VISUAL_PREFIX} from '../components/knowledge/PracticeVisuals';

const api=vi.hoisted(()=>({resources:vi.fn(),add:vi.fn(),progress:vi.fn(),save:vi.fn(),path:vi.fn(),ask:vi.fn()}));
vi.mock('../api/knowledgeExperience',()=>({getNodeResources:api.resources,addNodeResource:api.add,getNodeProgress:api.progress,saveNodeProgress:api.save,getKnowledgePath:api.path,askKnowledgeNode:api.ask}));
beforeEach(()=>{vi.clearAllMocks();api.resources.mockResolvedValue({items:[]});api.progress.mockResolvedValue({node_id:'n',status:'not_started',version:1});api.save.mockImplementation((_p,n,status)=>Promise.resolve({node_id:n,status,version:2}));});

test('rich links reject executable URLs and keep code and math intact',()=>{
 for(const url of ['javascript:alert(1)','data:text/html,test','//evil.test/a','https://user:pass@example.org/a','https://example.org/\\a']){expect(safeRichUrl(url)).toBeUndefined();expect(safeKnowledgeUrl(url)).toBeUndefined()}
 const {container}=render(<KnowledgeText text={'[官方教程](https://example.org/course)\n\n![示意图](https://example.org/image.png)\n\n$y=x^2$\n\n```python\nprint("[text](javascript:bad)")\n```'}/>);
 expect(screen.getByRole('link',{name:'官方教程'})).toHaveAttribute('href','https://example.org/course');
 expect(container.querySelector('img')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'查看图片'}));
 expect(screen.getByRole('img',{name:'示意图'})).toHaveAttribute('referrerpolicy','no-referrer');
 expect(container.querySelector('.katex')).not.toBeNull();expect(container.querySelector('code')).toHaveTextContent('[text](javascript:bad)');
 expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
});

test('video embed is allowlisted, loaded only on request, and has an external fallback',async()=>{
 expect(videoEmbed('https://youtube.com.evil.test/watch?v=aircAruvnKk')).toBeUndefined();expect(videoEmbed('http://www.youtube.com/watch?v=aircAruvnKk')).toBeUndefined();
 expect(videoEmbed('https://www.youtube.com/watch?v=aircAruvnKk')).toBe('https://www.youtube-nocookie.com/embed/aircAruvnKk');
 expect(videoEmbed('https://www.bilibili.com/video/BV1234567890')).toContain('autoplay=0');
 api.resources.mockResolvedValue({items:[{id:'v',title:'公开教学视频',type:'video',url:'https://www.youtube.com/watch?v=aircAruvnKk',fetched:false}]});
 const {container}=render(<ResourceExplorer projectId="p" nodeId="n"/>);
 expect(api.resources).not.toHaveBeenCalled();fireEvent.click(screen.getByText('图文、视频与代码资源',{selector:'summary'}));
 await screen.findByRole('link',{name:'公开教学视频'});expect(container.querySelector('iframe')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'点击播放视频'}));
 const frame=container.querySelector('iframe')!;expect(frame.src).not.toContain('autoplay=1');expect(frame).toHaveAttribute('sandbox','allow-scripts allow-same-origin allow-presentation');
 expect(screen.getByRole('link',{name:'打开原站视频'})).toHaveAttribute('href','https://www.youtube.com/watch?v=aircAruvnKk');
 fireEvent.click(screen.getByRole('button',{name:'关闭预览'}));expect(container.querySelector('iframe')).toBeNull();
});

test('resources support explicit scoped additions without pretending fetched content',async()=>{
 api.add.mockResolvedValue({id:'r'});render(<ResourceExplorer projectId="space" nodeId="node"/>);fireEvent.click(screen.getByText('图文、视频与代码资源',{selector:'summary'}));
 fireEvent.click(await screen.findByRole('button',{name:'添加资源链接'}));fireEvent.change(screen.getByLabelText('资源标题'),{target:{value:'原作者代码'}});fireEvent.change(screen.getByLabelText('资源地址'),{target:{value:'https://github.com/example/repo'}});fireEvent.change(screen.getByLabelText('添加的资源类型'),{target:{value:'code'}});
 fireEvent.click(screen.getByRole('button',{name:'保存到当前空间'}));await waitFor(()=>expect(api.add).toHaveBeenCalledWith('space','node',{title:'原作者代码',url:'https://github.com/example/repo',type:'code',reason:''}));
});

test('original image resources navigate back to their exact evidence',async()=>{
 const evidence={id:'e',source_id:'s',source_title:'原创资料',block_id:'b',quote:'图注',locator:{ordinal:2},source_version:'v',origin:'source'};
 api.resources.mockResolvedValue({items:[{id:'img',title:'图 1',type:'image',url:'/api/projects/p/sources/s/images/b',fetched:true,evidence}]});
 const onEvidence=vi.fn();render(<ResourceExplorer projectId="p" nodeId="n" onEvidence={onEvidence}/>);fireEvent.click(screen.getByText('图文、视频与代码资源',{selector:'summary'}));
 fireEvent.click(await screen.findByRole('button',{name:'定位原文'}));expect(onEvidence).toHaveBeenCalledWith(evidence);
});

test('learning progress changes only when the user chooses a state and sends expected version',async()=>{
 const listener=vi.fn();window.addEventListener('paperstride:learning-progress',listener);render(<LearningProgress projectId="p" nodeId="n"/>);
 await waitFor(()=>expect(screen.getByLabelText('我的学习状态')).toBeEnabled());expect(api.save).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('我的学习状态'),{target:{value:'understood'}});await waitFor(()=>expect(api.save).toHaveBeenCalledWith('p','n','understood',1));
 expect(await screen.findByText('自评记录与论文审核状态分别保存。')).toBeVisible();await waitFor(()=>expect(listener).toHaveBeenCalledOnce());window.removeEventListener('paperstride:learning-progress',listener);
});

test('prerequisite navigation uses returned edges and reports cyclic or bounded paths',async()=>{
 api.path.mockResolvedValue({nodes:[{id:'a',label:'前置 A'},{id:'n',label:'目标 N'}],edges:[{id:'e',explanation:'A 是 N 的已保存前置关系'}],paths:[{node_ids:['a','n'],edge_ids:['e']}],cycle_detected:true,truncated:true,message:'当前空间的前置路径'});
 const onNode=vi.fn();render(<LearningPath projectId="p" nodeId="n" onNode={onNode}/>);fireEvent.click(screen.getByText('沿图谱查看前置学习路径',{selector:'summary'}));
 fireEvent.click(await screen.findByRole('button',{name:'前置 A'}));expect(onNode).toHaveBeenCalledWith('a');expect(screen.getByRole('button',{name:'目标 N'})).toBeDisabled();expect(screen.getByRole('note')).toHaveTextContent('循环');expect(api.path).toHaveBeenCalledWith('p',{source:'n',kind:'prerequisites',max_depth:4},expect.any(AbortSignal));
});

test('node questions are explicit, scoped and return source links',async()=>{
 const citation={id:'e',source_id:'s',source_title:'论文 A',block_id:'b',quote:'Original evidence',locator:{page:3},source_version:'v',origin:'source'};
 api.ask.mockResolvedValue({answer:'依据说明',citations:[citation],node_ids:['n','other'],edge_ids:['edge'],model_used:false,origin:'source',warnings:[]});
 const onEvidence=vi.fn(),onNode=vi.fn();render(<NodeQuestion projectId="p" nodeId="n" onEvidence={onEvidence} onNode={onNode}/>);expect(api.ask).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('节点问题'),{target:{value:'解释依据'}});fireEvent.click(screen.getByRole('button',{name:'结合图谱与原文回答'}));
 await screen.findByText('依据说明');expect(api.ask).toHaveBeenCalledWith('p','n','解释依据',expect.any(AbortSignal));fireEvent.click(screen.getByRole('button',{name:'1. 论文 A · 第 3 页'}));expect(onEvidence).toHaveBeenCalledWith(citation);fireEvent.click(screen.getByText('查看回答涉及的图谱节点',{selector:'summary'}));fireEvent.click(screen.getByRole('button',{name:'定位关联节点 1'}));expect(onNode).toHaveBeenCalledWith('other');
});

test('late question response from a previous node cannot replace current node content',async()=>{
 let resolve!:(v:unknown)=>void;api.ask.mockImplementation(()=>new Promise(r=>{resolve=r}));const {rerender}=render(<NodeQuestion projectId="p" nodeId="old"/>);
 fireEvent.change(screen.getByLabelText('节点问题'),{target:{value:'旧问题'}});fireEvent.click(screen.getByRole('button',{name:'结合图谱与原文回答'}));rerender(<NodeQuestion projectId="p" nodeId="new"/>);
 await act(async()=>resolve({answer:'旧节点答案',citations:[],node_ids:[],warnings:[]}));expect(screen.queryByText('旧节点答案')).toBeNull();expect(screen.getByLabelText('节点问题')).toHaveValue('');
});

test('practice plots accept bounded finite data and never execute HTML',()=>{
 const data={type:'line',title:'缩放',series:[{name:'y',points:[[0,0],[1,2],[2,4]]}]};expect(validatePracticeVisual(data)?.series[0].points).toEqual(data.series[0].points);
 for(const value of [{...data,type:'html',html:'<script>bad()</script>'},{...data,series:[{points:[[0,Infinity]]}]},{type:'table',columns:['a'],rows:[[1,2]]},{...data,series:[{points:Array.from({length:501},()=>[0,0])}]}])expect(validatePracticeVisual(value)).toBeNull();
 const parsed=parsePracticeOutput('hello\n'+VISUAL_PREFIX+JSON.stringify(data)+'\n'+VISUAL_PREFIX+'{"type":"html"}');expect(parsed.visuals).toHaveLength(1);expect(parsed.text).toContain('hello');expect(parsed.warnings).toHaveLength(1);
 const {container}=render(<PracticeVisuals output={VISUAL_PREFIX+JSON.stringify(data)}/>);expect(screen.getByRole('img',{name:'缩放'})).toBeVisible();fireEvent.click(screen.getByText('查看绘图数据',{selector:'summary'}));expect(within(screen.getByRole('table')).getByText('4')).toBeVisible();expect(container.querySelector('script')).toBeNull();
});

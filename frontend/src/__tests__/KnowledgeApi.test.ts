import {beforeEach,expect,test,vi} from 'vitest';
import {attachKnowledgePaper,compareKnowledgeSources,getKnowledgeGraph,patchKnowledgeNode,patchNodeLearning,uploadKnowledgeSource} from '../api/knowledge';
import {setCsrfToken} from '../api/session';

const fetchMock=vi.fn();
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockImplementation(async()=>new Response('{}',{headers:{'Content-Type':'application/json'}}));setCsrfToken('workspace-csrf')});

test('source upload uses multipart with session protection and the requested project',async()=>{
 const file=new File(['study'],'study.md',{type:'text/markdown'});await uploadKnowledgeSource('space/a',file,'report');
 const [url,options]=fetchMock.mock.calls[0];expect(url).toContain('/api/projects/space%2Fa/sources');expect(options.body).toBeInstanceOf(FormData);expect(options.body.get('file').name).toBe('study.md');expect(options.body.get('kind')).toBe('report');expect(options.headers.get('X-Atlas-CSRF')).toBe('workspace-csrf');expect(options.headers.has('Content-Type')).toBe(false);expect(options.credentials).toBe('same-origin');
});
test('graph requests preserve source scope and encode search terms without mutations',async()=>{
 await getKnowledgeGraph('p',{source_id:'source/1',q:'arm & hand',node_id:'n',limit:100});const [url,options]=fetchMock.mock.calls[0];const u=new URL(url,'http://localhost');expect(u.searchParams.get('source_id')).toBe('source/1');expect(u.searchParams.get('q')).toBe('arm & hand');expect(options.method).toBe('GET');expect(options.body).toBeUndefined();
});
test('node edits carry version and report a conflict without silently retrying',async()=>{
 fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({detail:'内容已更新，请重新加载'}),{status:409,headers:{'Content-Type':'application/json'}}));await expect(patchKnowledgeNode('p','node/1',{expected_version:3,summary:'my correction'})).rejects.toThrow('内容已更新');expect(fetchMock).toHaveBeenCalledTimes(1);const [url,options]=fetchMock.mock.calls[0];expect(url).toContain('/nodes/node%2F1');expect(JSON.parse(options.body)).toEqual({expected_version:3,summary:'my correction'});
});
test('attaching a library paper submits its identity rather than arbitrary document paths',async()=>{
 await attachKnowledgePaper('p','paper-1');expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({paper_uid:'paper-1'});
});
test('comparison includes explicit method scope and learning correction uses a versioned PATCH',async()=>{
 await compareKnowledgeSources('p',['report','paper'],false,undefined,['report-d2']);expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({source_ids:['report','paper'],refresh:false,focus_node_ids:['report-d2']});await patchNodeLearning('p','node/1',{expected_revision:4,sections:{derivation:'正确的推导'},hidden_sections:['limitations']});const [url,options]=fetchMock.mock.calls[1];expect(url).toContain('/nodes/node%2F1/learning');expect(options.method).toBe('PATCH');expect(JSON.parse(options.body)).toEqual({expected_revision:4,sections:{derivation:'正确的推导'},hidden_sections:['limitations']});expect(options.headers.get('X-Atlas-CSRF')).toBe('workspace-csrf');
});

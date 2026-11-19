import {expect,test,vi} from 'vitest';
import {getUnifiedEdge} from '../api/unifiedGraph';
import {apiGet} from '../api/client';

vi.mock('../api/client',()=>({apiGet:vi.fn().mockResolvedValue({})}));

test('relation lookup carries the project scope needed for legacy ids',async()=>{
 const signal=new AbortController().signal;
 await getUnifiedEdge('42',signal,'space-one');
 expect(apiGet).toHaveBeenCalledWith('/api/knowledge/edges/42',{project_id:'space-one'},signal);
});

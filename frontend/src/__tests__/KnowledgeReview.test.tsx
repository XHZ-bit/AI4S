import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeReview from '../components/knowledge/KnowledgeReview';
import type {KnowledgeNode,KnowledgeEvidence} from '../api/knowledge';

const api=vi.hoisted(()=>({review:vi.fn(),history:vi.fn()}));
vi.mock('../api/knowledgeReview',()=>({reviewKnowledge:api.review,getKnowledgeHistory:api.history}));
const node:KnowledgeNode={id:'n',project_id:'p',source_id:'s',kind:'concept',label:'知识',summary:'说明',parent_id:null,origin:'source',research_status:'unspecified',version:3,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}};
const evidence:KnowledgeEvidence={id:'e',source_id:'s',source_title:'论文',block_id:'b',quote:'source',locator:{page:2},source_version:'v1',origin:'source'};
beforeEach(()=>{vi.clearAllMocks();api.review.mockResolvedValue({status:'human_verified',record:node});api.history.mockResolvedValue({items:[]})});

test('review and history stay out of the primary interface and load only on demand',async()=>{
 render(<KnowledgeReview projectId="p" record={node} evidence={[evidence]} onSaved={vi.fn()}/>);
 expect(screen.queryByLabelText('核对说明')).toBeNull();expect(api.history).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('依据核对与修订历史'));
 await screen.findByLabelText('核对说明');
 expect(api.history).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('查看历史版本'));
 await waitFor(()=>expect(api.history).toHaveBeenCalledWith('p','n',expect.any(AbortSignal)));
});

test('a stale or missing evidence cannot be verified but users can record a question',async()=>{
 const saved=vi.fn();render(<KnowledgeReview projectId="p" record={{...node,quality_review_stale:true}} evidence={[{...evidence,source_changed:true}]} onSaved={saved}/>);
 fireEvent.click(screen.getByText('依据核对与修订历史'));
 fireEvent.change(await screen.findByLabelText('核对说明'),{target:{value:'原文条件需要重新确认'}});
 expect(screen.getByRole('button',{name:'我已核对原文'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'标记疑问'}));
 await waitFor(()=>expect(saved).toHaveBeenCalledOnce());
 expect(api.review).toHaveBeenCalledWith('p',expect.objectContaining({id:'n',version:3}),'dispute','原文条件需要重新确认');
});

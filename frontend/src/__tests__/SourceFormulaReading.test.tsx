import {fireEvent, render, screen} from '@testing-library/react';
import {expect, test, vi} from 'vitest';
import {SourceReader} from '../components/knowledge/KnowledgeSources';

const api=vi.hoisted(()=>({source:vi.fn(),node:vi.fn()}));
vi.mock('../api/knowledge',async()=>{
  const actual=await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge');
  return {...actual,getKnowledgeSource:api.source,getKnowledgeNode:api.node};
});
vi.mock('../components/workspace/PdfReader',()=>({default:()=> <div>原文页面</div>}));

test('the original reader opens saved formula symbols on demand and preserves its source position',async()=>{
  const evidence={id:'e',source_id:'s',source_title:'Attention',block_id:'b',quote:'scaled score',locator:{page:4},source_version:'v1',origin:'source'};
  api.source.mockResolvedValue({id:'s',title:'Attention',kind:'paper',filename:'paper.pdf',media_type:'application/pdf',version:'v1',
    blocks:[{id:'b',page:4,text:'scaled score',metadata:{}}],knowledge_nodes:[{id:'n',label:'缩放分数',kind:'formula',block_ids:['b']}]});
  api.node.mockResolvedValue({node:{id:'n',metadata:{symbols:{Q:{meaning:'查询矩阵',shape:'n × d_k'}},conditions:'维度需要与键向量一致'}},evidence:[evidence]});
  const onLearn=vi.fn(),onEvidence=vi.fn();
  render(<SourceReader projectId="p" sourceId="s" page={4} blockId="b" onLearn={onLearn} onEvidence={onEvidence}/>);
  await screen.findByRole('button',{name:'学习这条公式'});
  expect(api.node).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('查看公式符号与条件',{selector:'summary'}));
  await screen.findByText('查询矩阵');
  expect(screen.getByText('n × d_k')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'核对符号原文'}));
  expect(onEvidence).toHaveBeenCalledWith(evidence);
  fireEvent.click(screen.getByRole('button',{name:'继续理解本式'}));
  expect(onLearn).toHaveBeenCalledWith('n',{block:'b',page:4});
});

test('a textual original with a bare formula renders even without metadata.latex',async()=>{
 const formula=String.raw`\begin{aligned}\mathrm{MultiHead}(Q,K,V)&=\mathrm{Concat}(h_1,h_2)W^O\\h_i&=\frac{QK^T}{\sqrt{d_k}}\end{aligned}`;
 api.source.mockResolvedValue({id:'text',title:'自编注意力资料',kind:'report',filename:'attention.md',media_type:'text/markdown',version:'v1',
  blocks:[{id:'formula',ordinal:0,kind:'text',heading:'多头注意力',text:formula,page:null,metadata:{}}],knowledge_nodes:[]});
 const {container}=render(<SourceReader projectId="p" sourceId="text"/>);
 await screen.findByRole('heading',{name:'多头注意力'});
 expect(container.querySelectorAll('.katex-display')).toHaveLength(1);
 expect(container.querySelector('annotation')?.textContent).toBe(formula);
});

test('the code reader preserves mathematical-looking source strings verbatim',async()=>{
 const code=String.raw`formula = "\begin{aligned}x&=y\end{aligned}" # $x$`;
 api.source.mockResolvedValue({id:'code',title:'教学源码',kind:'code',filename:'model.py',media_type:'text/plain',version:'v1',
  blocks:[{id:'line',ordinal:0,kind:'code',heading:'源码',text:code,page:null,metadata:{path:'model.py',start_line:1,end_line:1}}],knowledge_nodes:[]});
 const {container}=render(<SourceReader projectId="p" sourceId="code"/>);
 await screen.findByRole('heading',{name:'源码'});
 expect(container.querySelector('.kw-code-lines code')?.textContent).toBe(code);
 expect(container.querySelector('.katex')).toBeNull();
});

test('an explicitly typed formula block renders its saved expression without a redundant latex field',async()=>{
 api.source.mockResolvedValue({id:'formula-only',title:'公式资料',kind:'report',filename:'equations.md',media_type:'text/markdown',version:'v1',
  blocks:[{id:'equation',ordinal:0,kind:'formula',heading:'已知公式',text:'y=x^2',page:null,metadata:{}}],knowledge_nodes:[]});
 const {container}=render(<SourceReader projectId="p" sourceId="formula-only"/>);
 await screen.findByRole('heading',{name:'已知公式'});
 expect(container.querySelectorAll('.katex-display')).toHaveLength(1);
 expect(container.querySelector('annotation')?.textContent).toBe('y=x^2');
});

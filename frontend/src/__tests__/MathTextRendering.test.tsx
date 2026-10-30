import {fireEvent,render,screen} from '@testing-library/react';
import {expect,test,vi} from 'vitest';
import MathText from '../components/learning/MathText';
import SourceFormulas from '../components/knowledge/SourceFormulas';
import type {FormulaSource,KnowledgeEvidence} from '../api/knowledge';

test('dollar and bracket math delimiters all render as mathematical notation',()=>{
 const {container}=render(<MathText text={String.raw`Inline $x_t$ and \(y^2\). Display $$x+y$$ and \[\frac{a}{b}\].`}/>);
 expect(container.querySelectorAll('.katex').length).toBe(4);
 expect(container.querySelectorAll('.katex-display').length).toBe(2);
 expect(container.querySelector('.katex-error')).toBeNull();
});
test('damaged PDF glyph runs do not become a long page of fragments and prose is kept',()=>{
 const {container}=render(<MathText text={'This is an actual explanation.\n\nc_t=fcoord\n�\nsb,p\nt\n�'}/>);
 expect(screen.getByText('This is an actual explanation.')).toBeVisible();
 expect(screen.getByRole('note')).toHaveTextContent('公式文本识别不完整');
 expect(container.textContent).not.toContain('�');
});
test('JSON-decoded math control characters are never rendered as valid notation',()=>{
 const broken='策略 $'+String.fromCharCode(8)+'eta(a|s)$';
 const {container}=render(<MathText text={broken}/>);
 expect(screen.getByRole('note')).toHaveTextContent('公式文本识别不完整');
 expect(container.querySelector('.katex')).toBeNull();expect(container.textContent).not.toContain(String.fromCharCode(8));
});
const source:FormulaSource={evidence_id:'e1',block_id:'b1',source_id:'s1',label:'Method',page:5,latex:'',recognition:'source_image',image_url:'/api/projects/p/sources/s1/images/b1'};
const evidence={id:'e1',source_id:'s1',block_id:'b1',quote:'bad glyphs',source_title:'Actual PDF',locator:{page:5,bbox:[1,2,3,4]}} as KnowledgeEvidence;
test('untranscribed formula renders the precise source crop with a working original link',()=>{
 const open=vi.fn();render(<SourceFormulas items={[source]} evidence={[evidence]} onEvidence={open}/>);
 expect(screen.getByRole('img',{name:'第 5 页公式原图'})).toHaveAttribute('src',source.image_url);
 expect(screen.queryByText('bad glyphs')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'查看公式原文'}));expect(open).toHaveBeenCalledWith(evidence);
});
test('source latex renders once while the original crop stays available for checking',()=>{
 const {container}=render(<SourceFormulas items={[{...source,latex:String.raw`\frac{x}{2}`}]} evidence={[evidence]} onEvidence={vi.fn()}/>);
 expect(container.querySelectorAll('.katex').length).toBe(1);expect(screen.getByText('核对公式原图')).toBeVisible();
});
test('no formula source produces no empty heading or placeholder',()=>{
 const {container}=render(<SourceFormulas items={[]} evidence={[]} onEvidence={vi.fn()}/>);expect(container).toBeEmptyDOMElement();
});
test('unsupported formula syntax falls back to the actual source instead of exposing broken TeX',()=>{
 const {container}=render(<SourceFormulas items={[{...source,latex:String.raw`\notARealMathCommand{x}`}]} evidence={[evidence]} onEvidence={vi.fn()}/>);
 expect(container.querySelector('.katex-error')).toBeNull();expect(container.textContent).not.toContain('notARealMathCommand');expect(screen.getByRole('img')).toHaveAttribute('src',source.image_url);
});

import {fireEvent,render,screen} from '@testing-library/react';
import {expect,test,vi} from 'vitest';
import MathText,{displayMath} from '../components/learning/MathText';
import KnowledgeText,{mathAwareText} from '../components/knowledge/KnowledgeText';
import FormulaContext from '../components/knowledge/FormulaContext';
import EvidenceQuote from '../components/knowledge/EvidenceQuote';
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

const multiHead=String.raw`\begin{aligned}
\mathrm{MultiHead}(Q,K,V)&=\mathrm{Concat}(\mathrm{head}_1,\ldots,\mathrm{head}_h)W^O\\

\mathrm{head}_i&=\operatorname{Attention}(QW_i^Q,KW_i^K,VW_i^V)\\
W_i^Q&=\begin{bmatrix}1&0\\0&1\end{bmatrix}
\end{aligned}`;

test('bare aligned with blank lines and nested matrices renders as one complete formula without metadata',()=>{
 const text='先看多头注意力的计算。\n\n'+multiHead+'\n\n再核对输出投影。';
 const {container}=render(<KnowledgeText text={text}/>);
 expect(container).toHaveTextContent('先看多头注意力的计算。');
 expect(container).toHaveTextContent('再核对输出投影。');
 expect(container.querySelectorAll('.katex-display')).toHaveLength(1);
 expect(container.querySelector('annotation[encoding="application/x-tex"]')?.textContent).toBe(multiHead);
 expect(container.querySelector('.learning-math-fallback')).toBeNull();
});

test.each([
 String.raw`\begin{align}x&=y\\z&=1\end{align}`,
 String.raw`\begin{gathered}x=y\\z=1\end{gathered}`,
 String.raw`\begin{cases}x&x>0\\0&x\le0\end{cases}`,
 String.raw`\begin{pmatrix}1&0\\0&1\end{pmatrix}`,
 String.raw`\begin{array}{cc}1&2\\3&4\end{array}`,
 String.raw`\frac{QK^{T}}{\sqrt{d_k}}`,
 String.raw`y = \frac{x}{\sqrt{d_k}}`,
])('unambiguous bare mathematical syntax renders without requiring a latex field: %s',formula=>{
 const {container}=render(<MathText text={formula}/>);
 expect(container.querySelectorAll('.katex')).toHaveLength(1);
 expect(container.querySelector('.katex-error')).toBeNull();
 expect(container.querySelector('annotation')?.textContent).toBe(formula);
});

test('metadata that already has delimiters is not wrapped a second time',()=>{
 const latex=String.raw`\[\frac{x}{2}\]`;
 expect(displayMath(latex)).toBe(latex);expect(mathAwareText(latex,latex)).toBe(latex);
 const {container}=render(<SourceFormulas items={[{...source,latex}]} evidence={[evidence]} onEvidence={vi.fn()}/>);
 expect(container.querySelectorAll('.katex')).toHaveLength(1);
 expect(container.querySelector('annotation')?.textContent).toBe(String.raw`\frac{x}{2}`);
});

test('unsupported bare TeX has a compact failure and an exact on-demand original',()=>{
 const original=String.raw`\begin{aligned}y&=\notARealMathCommand{x}\end{aligned}`;
 const {container}=render(<KnowledgeText text={'这段解释保留。\n\n'+original}/>);
 expect(container).toHaveTextContent('这段解释保留。');
 expect(container.textContent).not.toContain('notARealMathCommand');
 const button=screen.getByRole('button',{name:'查看原式'});
 expect(button).toHaveAttribute('aria-expanded','false');fireEvent.click(button);
 expect(container.querySelector('.learning-math-original')?.textContent).toBe(original);
 fireEvent.click(screen.getByRole('button',{name:'收起原式'}));
 expect(container.querySelector('.learning-math-original')).toBeNull();
});

test.each([
 '$'+String.fromCharCode(9)+'heta$',
 '$'+String.fromCharCode(13)+'ho$',
 '$x\ny$',
 String.raw`\\begin{aligned}x&=y\end{aligned}`,
 String.raw`\begin{aligned}x&=y`,
])('damaged or incomplete math is never silently repaired: %s',original=>{
 const {container}=render(<KnowledgeText text={original}/>);
 expect(container.querySelector('.katex')).toBeNull();
 expect(container.querySelector('.learning-math-fallback')).not.toBeNull();
 expect(container.querySelector('.katex-error')).toBeNull();
});

test('Windows line endings in complete display math are valid without changing the stored expression',()=>{
 const original=multiHead.replace(/\n/g,'\r\n');
 const {container}=render(<MathText text={original}/>);
 expect(container.querySelectorAll('.katex-display')).toHaveLength(1);
 expect(container.querySelector('annotation')?.textContent).toBe(multiHead);
 expect(original).toContain('\r\n');
});

test('literal code and code evidence never reinterpret dollars, escapes, or math environments',()=>{
 const code=String.raw`formula = "\begin{aligned}x&=y\end{aligned}" # $not_math$`;
 const {container}=render(<><KnowledgeText text={'```python\n'+code+'\n```\n\n`'+String.raw`\frac{x}{2}`+'`'}/><EvidenceQuote evidence={{...evidence,quote:code,locator:{path:'model.py',start_line:8,end_line:8}}}/></>);
 expect(container.querySelectorAll('.katex')).toHaveLength(0);
 expect(container.querySelector('.kw-learning-code code')?.textContent).toBe(code);
 expect(container.querySelector('.kw-evidence-code code')?.textContent).toBe(code);
 expect(container.querySelector('.learning-math-fallback')).toBeNull();
});

test('symbols, meanings, dimensions and conditions share mathematical rendering',()=>{
 const {container}=render(<FormulaContext metadata={{symbols:{d_k:{meaning:String.raw`缩放量 $\sqrt{d_k}$`,shape:String.raw`$n\times d_k$`}},conditions:'$d_k>0$'}}/>);
 expect(container.querySelectorAll('.katex')).toHaveLength(4);
 expect(container.querySelectorAll('dt .katex')).toHaveLength(1);
 expect(container).toHaveTextContent('缩放量');
});

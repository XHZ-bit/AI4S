import {useState} from 'react';
import {Button, InputNumber} from 'antd';
import MathText from '../learning/MathText';
import './foundation-demos.css';

export const FOUNDATION_DEMOS: Record<string, {title: string; note: string}> = {
  dot_product: {title: '从两个特征向量算点积', note: '逐个分量相乘、相加，观察每一项对总分的贡献。'},
  scaled_attention: {title: '从点积分数到注意力权重', note: '使用三个候选位置，分别显示原分数、缩放分数与softmax权重。'},
  softmax: {title: '一组分数怎样变成权重', note: '改变一个候选或同时平移所有分数，检查权重怎样变化。'},
  probability: {title: '概率与有限次观察', note: '教学袋中每个球被等可能抽到，模拟有放回抽样。'},
  research_design: {title: '检查两组研究条件', note: '用自编的学习方式比较，核对时长、测试间隔和分组方式。'},
  sampling: {title: '样本结果能够说明谁', note: '同时查看总体、实际观察对象、样本计数和抽样方式。'},
};

export function stableSoftmax(scores: number[]): number[] {
  if (!scores.length || scores.some(value => !Number.isFinite(value))) return [];
  const maximum = Math.max(...scores);
  const exponentials = scores.map(value => Math.exp(value - maximum));
  const sum = exponentials.reduce((total, value) => total + value, 0);
  return exponentials.map(value => value / sum);
}

function NumberField({label, value, onChange, min = -1000, max = 1000, step = 1}: {
  label: string; value: number; onChange: (value: number) => void; min?: number; max?: number; step?: number;
}) {
  return <label className="kw-foundation-number"><span>{label}</span><InputNumber aria-label={label} value={value}
    min={min} max={max} step={step} onChange={next => {
      if (typeof next === 'number' && Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
    }}/></label>;
}

function DotProduct() {
  const [q, setQ] = useState([1, 2]);
  const [k, setK] = useState([2, 3]);
  const contributions = q.map((value, index) => value * k[index]);
  const total = contributions.reduce((sum, value) => sum + value, 0);
  return <div className="kw-foundation-demo">
    <p>这里固定两个维度。请先预测改变一个分量后，总分会怎样变化。</p>
    <div className="kw-foundation-inputs">{q.map((value, index) => <NumberField key={'q'+index} label={'查询分量 q'+(index+1)} value={value}
      onChange={next => setQ(old => old.map((item, i) => i === index ? next : item))}/>)}
      {k.map((value, index) => <NumberField key={'k'+index} label={'键分量 k'+(index+1)} value={value}
        onChange={next => setK(old => old.map((item, i) => i === index ? next : item))}/>)}</div>
    <table className="kw-foundation-table"><caption>逐维计算</caption><thead><tr><th>位置</th><th>查询分量</th><th>键分量</th><th>乘积</th></tr></thead>
      <tbody>{contributions.map((value, index) => <tr key={index}><th>{index+1}</th><td>{q[index]}</td><td>{k[index]}</td><td>{value.toFixed(3)}</td></tr>)}</tbody></table>
    <p className="kw-foundation-result" role="status">点积 <strong>{total.toFixed(3)}</strong></p>
    <p>同位置的特征需要对应。当前数值是教学打分，范围取决于输入，原文中的向量维度和后续步骤需要另外核对。</p>
  </div>;
}

function ScoreWeights({scaled}: {scaled: boolean}) {
  const [scores, setScores] = useState(scaled ? [8, 4, 0] : [4, 2, 0]);
  const [dimensions, setDimensions] = useState(4);
  const normalized = scaled ? scores.map(value => value / Math.sqrt(dimensions)) : scores;
  const weights = stableSoftmax(normalized);
  return <div className="kw-foundation-demo">
    <div className="kw-foundation-inputs">{scores.map((value, index) => <NumberField key={index} label={(scaled ? '点积分数 ' : '候选分数 ')+(index+1)} value={value}
      onChange={next => setScores(old => old.map((item, i) => i === index ? next : item))}/>)}
      {scaled && <NumberField label="键向量维度 d_k" value={dimensions} min={1} max={4096} onChange={next => setDimensions(Math.round(next))}/>}</div>
    <MathText text={scaled ? '$$s_i=(q^T k_i)/\\sqrt{d_k},\\qquad p_i=\\exp(s_i)/\\sum_j\\exp(s_j)$$' : '$$p_i=\\exp(s_i)/\\sum_j\\exp(s_j)$$'}/>
    {!scaled && <Button disabled={scores.some(value => value > 990)} onClick={() => setScores(old => old.map(value => value + 10))}>所有分数同时加10</Button>}
    <table className="kw-foundation-table"><caption>{scaled ? '先缩放，再计算整组权重' : '各候选的归一化权重'}</caption>
      <thead><tr><th>候选</th><th>{scaled ? '点积分数' : '原分数'}</th>{scaled && <th>缩放分数</th>}<th>权重</th></tr></thead>
      <tbody>{scores.map((value, index) => <tr key={index}><th>位置 {index+1}</th><td>{value.toFixed(3)}</td>{scaled && <td data-testid={'scaled-score-'+index}>{normalized[index].toFixed(4)}</td>}
        <td><div className="kw-foundation-weight"><span>{weights[index].toFixed(4)}</span><span className="kw-foundation-bar" aria-hidden="true"><i style={{width:(weights[index]*100)+'%'}}/></span></div></td></tr>)}</tbody>
    </table>
    <p role="status">权重总和 {weights.reduce((sum, value) => sum + value, 0).toFixed(4)}</p>
    <p>{scaled ? '教学输入默认给出4.0这一缩放分数；后面的权重由三个分数一起决定。完整注意力输出还要按权重对V加权求和。' : '同时给所有分数加相同常数，权重保持相同。有限精度下极小的权重可能显示为0，计算使用减去最大值的形式。'}</p>
  </div>;
}

function Probability() {
  const [counts, setCounts] = useState([3, 2, 1]);
  const [observations, setObservations] = useState<number[]>([]);
  const names = ['红球', '蓝球', '白球'];
  const total = counts.reduce((sum, value) => sum + value, 0);
  const draw = () => {
    const result = [0, 0, 0];
    for (let i = 0; i < 12; i++) {
      const selected = Math.random() * total;
      const index = selected < counts[0] ? 0 : selected < counts[0] + counts[1] ? 1 : 2;
      result[index]++;
    }
    setObservations(result);
  };
  return <div className="kw-foundation-demo">
    <div className="kw-foundation-inputs">{counts.map((value, index) => <NumberField key={index} label={names[index]+'数量'} value={value} min={0} max={50}
      onChange={next => {setCounts(old => old.map((item, i) => i === index ? Math.round(next) : item)); setObservations([]);}}/>)}</div>
    {total ? <><table className="kw-foundation-table"><caption>袋中总数 {total} 个，每个球等可能被抽到</caption>
      <thead><tr><th>事件</th><th>单次抽到的概率</th><th>本次12次计数</th><th>本次观察频率</th></tr></thead>
      <tbody>{counts.map((value, index) => <tr key={index}><th>{names[index]}</th><td>{(value/total).toFixed(4)}</td><td>{observations.length ? observations[index] : '尚未抽取'}</td><td>{observations.length ? (observations[index]/12).toFixed(4) : '尚未抽取'}</td></tr>)}</tbody>
    </table><Button onClick={draw}>有放回抽取12次</Button>{!!observations.length && <p role="status">本次抽取已完成，共 {observations.reduce((sum, value) => sum+value, 0)} 次。</p>}</> : <p role="status">袋中至少需要1个球，才能定义本次抽取。</p>}
    <p>每次抽完都放回，袋中比例保持相同。有限次数的观察频率会波动，论文中的随机机制需要按原文确认。</p>
  </div>;
}

function ResearchDesign() {
  const [durationA, setDurationA] = useState(5);
  const [durationB, setDurationB] = useState(10);
  const [intervalA, setIntervalA] = useState('即时');
  const [intervalB, setIntervalB] = useState('一周');
  const [allocation, setAllocation] = useState('自选');
  const differences = [
    durationA !== durationB ? '两组学习时长不同，观察到的差异可能与学习时间有关。' : '',
    intervalA !== intervalB ? '两组测试间隔不同，需要分别讨论即时表现与延迟表现。' : '',
    allocation === '自选' ? '参与者自主选择学习方式，原有动机或基础可能影响组间比较。' : '',
  ].filter(Boolean);
  return <div className="kw-foundation-demo">
    <p>自编教学问题是“重复阅读和主动回忆的结果怎样比较”。比较因素为学习方式，测量结果为随后回忆出的项目数。</p>
    <div className="kw-foundation-inputs"><NumberField label="阅读组学习分钟" value={durationA} min={1} max={60} onChange={setDurationA}/>
      <NumberField label="回忆组学习分钟" value={durationB} min={1} max={60} onChange={setDurationB}/>
      <label>阅读组测试间隔<select aria-label="阅读组测试间隔" value={intervalA} onChange={event => setIntervalA(event.target.value)}><option>即时</option><option>一周</option></select></label>
      <label>回忆组测试间隔<select aria-label="回忆组测试间隔" value={intervalB} onChange={event => setIntervalB(event.target.value)}><option>即时</option><option>一周</option></select></label>
      <label>进入各组的方式<select aria-label="进入各组的方式" value={allocation} onChange={event => setAllocation(event.target.value)}><option value="自选">参与者自主选择</option><option value="随机">参与者随机分配</option></select></label></div>
    <section className="kw-foundation-feedback" aria-label="研究条件反馈"><h5>需要核对的条件</h5>{differences.length ? <ul>{differences.map(item => <li key={item}>{item}</li>)}</ul> : <p>列出的时间条件已对齐，分组采用随机分配。</p>}
      <p>还需核对材料、测量办法、样本规模、执行过程和统计不确定性。随机分配有助于减少分组选择带来的混杂。</p></section>
  </div>;
}

function Sampling() {
  const [population, setPopulation] = useState(1000);
  const [sample, setSample] = useState(100);
  const [support, setSupport] = useState(30);
  const [method, setMethod] = useState('volunteer');
  return <div className="kw-foundation-demo">
    <div className="kw-foundation-inputs"><NumberField label="总体人数 N" value={population} min={1} max={100000} onChange={next => {const size=Math.round(next);setPopulation(size);setSample(old=>Math.min(old,size));setSupport(old=>Math.min(old,size));}}/>
      <NumberField label="实际样本量 n" value={sample} min={1} max={population} onChange={next => {const size=Math.round(next);setSample(size);setSupport(old=>Math.min(old,size));}}/>
      <NumberField label="样本中支持人数 k" value={support} min={0} max={sample} onChange={next=>setSupport(Math.round(next))}/>
      <label>抽样方式<select aria-label="抽样方式" value={method} onChange={event=>setMethod(event.target.value)}><option value="volunteer">志愿报名</option><option value="random">从总体随机抽取</option></select></label></div>
    <p className="kw-foundation-result" role="status">样本支持比例 <strong>{(100*support/sample).toFixed(1)}%</strong></p>
    <p>实际观察 {sample} 人，总体 {population} 人，尚未观察 {population-sample} 人。</p>
    <section className="kw-foundation-feedback" aria-label="抽样范围反馈"><h5>怎样解释当前结果</h5><p>{method==='volunteer' ? '本教学样本来自志愿者，需要关注报名意愿与研究问题之间的关系。增加同一报名渠道的样本仍可能保留选择偏差。' : '随机抽取为向给定总体推断提供了设计依据，仍需核对抽样框、未回应和抽样不确定性。'}</p><p>这里的百分比描述已观察的样本。论文的结论范围还取决于实际参与者和研究条件。</p></section>
  </div>;
}

export default function FoundationDemos({topic}: {topic: string}) {
  switch (topic) {
    case 'dot_product': return <DotProduct/>;
    case 'scaled_attention': return <ScoreWeights scaled/>;
    case 'softmax': return <ScoreWeights scaled={false}/>;
    case 'probability': return <Probability/>;
    case 'research_design': return <ResearchDesign/>;
    case 'sampling': return <Sampling/>;
    default: return null;
  }
}

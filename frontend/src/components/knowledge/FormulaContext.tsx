import {Button} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import MathText,{inlineMath} from '../learning/MathText';
import './formula-context.css';

function text(value: unknown): string {
  if (typeof value === 'string') return value.slice(0, 1200);
  if (typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join('、').slice(0, 1200);
  return '';
}

export function formulaSymbols(metadata: Record<string, unknown>) {
  const raw = metadata.symbols;
  const entries = Array.isArray(raw) ? raw.map(item => ['', item]) : raw && typeof raw === 'object' ? Object.entries(raw) : [];
  return entries.slice(0, 20).flatMap(([key, value]) => {
    if (typeof value === 'string') return [{symbol: text(key) || value, meaning: key ? value : '', detail: ''}];
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    const item = value as Record<string, unknown>;
    const symbol = text(item.symbol || item.name || key);
    if (!symbol) return [];
    const meaning = text(item.meaning || item.definition || item.description);
    const detail = [text(item.shape || item.dimensions || item.dimension), text(item.unit || item.units)].filter(Boolean).join(' · ');
    return [{symbol, meaning, detail}];
  });
}

export default function FormulaContext({metadata, evidence = [], onEvidence, onLearn, showEmpty = false}: {
  metadata: Record<string, unknown>;
  evidence?: KnowledgeEvidence[];
  onEvidence?: (value: KnowledgeEvidence) => void;
  onLearn?: () => void;
  showEmpty?: boolean;
}) {
  const symbols = formulaSymbols(metadata);
  const conditions = [text(metadata.conditions), text(metadata.assumptions)].filter(Boolean);
  if (!symbols.length && !conditions.length && !showEmpty) return null;
  return <section className="kw-formula-context" aria-label="本式符号与条件">
    <h3>本式符号与条件</h3>
    {symbols.length ? <dl>{symbols.map((item, index) => <div key={item.symbol + index}><dt><MathText text={inlineMath(item.symbol)} showSourceOnError/></dt><dd><MathText text={item.meaning || '含义尚待对照原文'} showSourceOnError/>{item.detail && <small><MathText text={item.detail} showSourceOnError/></small>}</dd></div>)}</dl> : <p>当前资料尚未提取本式的符号说明，可以结合公式原图继续核对。</p>}
    {conditions.map((condition, index) => <p key={index}><MathText text={condition} showSourceOnError/></p>)}
    <small>根据当前知识点的已保存说明整理，需结合原文核对。</small>
    {(onLearn || onEvidence && evidence[0]) && <div className="kw-formula-context-actions">{onEvidence && evidence[0] && <Button size="small" onClick={() => onEvidence(evidence[0])}>核对符号原文</Button>}{onLearn && <Button size="small" type="primary" onClick={onLearn}>继续理解本式</Button>}</div>}
  </section>;
}

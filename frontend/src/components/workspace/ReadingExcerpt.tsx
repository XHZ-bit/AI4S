import "./reading-excerpt.css";

export function readingPrompt(text: string, heading = "") {
  const source = `${heading} ${text}`.toLowerCase();
  if (/experiment|evaluation|benchmark|result|实验|评估|结果/.test(source)) return "先找实验的数据、比较对象和评价指标，再核对结论在哪些条件下成立。表格数值请在原文中查看。";
  if (/method|model|policy|algorithm|方法|模型|算法/.test(source)) return "先辨认方法的输入、输出和执行步骤，再查看公式中的变量含义与假设。公式请以 PDF 版面为准。";
  if (/limit|discussion|future|限制|讨论/.test(source)) return "区分作者已经验证的结果与尚待验证的解释，记录方法的适用范围和开放问题。";
  return "阅读对应原文，记下这一段的问题、关键概念和支持它的证据；遇到公式时先核对变量定义与上下文。";
}

export default function ReadingExcerpt({text, heading = "", compact = false}: {text: string; heading?: string; compact?: boolean}) {
  const lines = text.split(/\n/).filter(line => line.trim());
  const noisy = lines.filter(line => line.trim().length < 12).length > Math.max(3, lines.length * .3)
    || /[∑∏∫�]|\\(?:frac|sum|begin|alpha|theta)|\$\$/.test(text);
  return <section className={`atlas-reading-excerpt${compact ? " is-compact" : ""}`} aria-label="原文阅读建议">
    <strong>阅读建议</strong>
    <p>{readingPrompt(text, heading)}</p>
    <details><summary>查看解析文字{noisy ? "（含公式或版面碎片）" : ""}</summary>
      <p className="atlas-excerpt-caution">解析文字用于检索和定位，可能丢失公式、上下标及排版，请结合原文核对。</p>
      <blockquote>{text}</blockquote>
    </details>
  </section>;
}

import type {KnowledgeEvidence} from '../../api/knowledge';
import MathText from '../learning/MathText';

/** Source code is literal evidence, not prose to reinterpret as mathematics. */
export default function EvidenceQuote({evidence}:{evidence:KnowledgeEvidence}){
 const code=!!evidence.locator?.path||typeof evidence.locator?.start_line==='number';
 return code?<pre className="kw-evidence-code"><code>{evidence.quote}</code></pre>:<MathText text={evidence.quote} showSourceOnError/>;
}

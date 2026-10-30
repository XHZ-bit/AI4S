import type {AccessLink} from '../api/graph';

export default function ResourceAccess({links=[]}:{links?:AccessLink[]}) {
  if(!links.length)return null;
  return <nav aria-label="资源访问链接" style={{display:'flex',flexWrap:'wrap',gap:'8px 18px',margin:'12px 0'}}>
    {links.map(link=><a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer" title={link.note||undefined}>{link.label} ↗</a>)}
  </nav>;
}

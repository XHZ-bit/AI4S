import {AutoComplete} from 'antd';
import {DOMAIN_PROFILES} from '../../api/project-types';
import type {DomainId} from '../../api/project-types';

export function researchDomainValue(domain?:DomainId,custom?:string|null){
 return domain&&domain!=='custom'?DOMAIN_PROFILES[domain].label:custom||'';
}
export function parseResearchDomain(value?:string){
 const text=(value||'').trim();
 const profile=Object.values(DOMAIN_PROFILES).find(p=>p.id!=='custom'&&(p.label===text||p.id===text));
 return profile?{domain:profile.id,custom_domain:null}:{domain:'custom' as const,custom_domain:text||null};
}
export default function ResearchDomainInput({value,onChange,id}:{value?:string;onChange?:(value:string)=>void;id?:string}){
 return <AutoComplete id={id} aria-label="研究领域" value={value} onChange={onChange} maxLength={150}
  options={Object.values(DOMAIN_PROFILES).filter(p=>p.id!=='custom').map(p=>({value:p.label}))}
  filterOption={(input,option)=>String(option?.value).toLowerCase().includes(input.toLowerCase())}
  placeholder="直接输入研究领域，也可选择建议" allowClear/>;
}

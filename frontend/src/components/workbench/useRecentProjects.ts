import {useEffect,useState} from 'react';
import {listProjects} from '../../api/projects';
import type {ResearchProject} from '../../api/project-types';
import {useCurrentAccount} from '../SessionContext';

const requests = new Map<string, {promise:Promise<ResearchProject[]>; expires:number}>();
function recentProjects(account:string, refresh=false) {
  const prior=requests.get(account);
  if(prior && (prior.expires===Infinity || (!refresh && prior.expires>Date.now())))return prior.promise;
  const entry={promise:Promise.resolve([] as ResearchProject[]),expires:Infinity};
  entry.promise=listProjects({status:'active',limit:100}).then(result=>{
    entry.expires=Date.now()+30_000;
    return result.items.slice().sort((a,b)=>b.updated_at.localeCompare(a.updated_at)).slice(0,5);
  }).catch(error=>{if(requests.get(account)===entry)requests.delete(account);throw error;});
  requests.set(account,entry);return entry.promise;
}

/** Shell and workbench share one account-scoped, in-flight project request. */
export default function useRecentProjects(){
  const account=useCurrentAccount()?.id||'local';
  const [state,setState]=useState<{account:string;items:ResearchProject[];loading:boolean;error:string}>({account,items:[],loading:true,error:''});
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    let live=true,generation=0;
    const load=(refresh=false)=>{const request=++generation;setState(old=>({...old,account,items:old.account===account?old.items:[],loading:true,error:''}));
      recentProjects(account,refresh).then(items=>{if(live&&request===generation)setState({account,items,loading:false,error:''})}).catch(e=>{if(live&&request===generation)setState(old=>({...old,account,loading:false,error:String(e)}))});};
    const update=()=>load(true);load(retry>0);window.addEventListener('atlas:data-change',update);
    return()=>{live=false;window.removeEventListener('atlas:data-change',update);};
  },[account,retry]);
  return {...(state.account===account?state:{account,items:[],loading:true,error:''}),retry:()=>setRetry(v=>v+1)};
}

import {useEffect,useState} from 'react';
import {usePreferences} from '../PreferencesContext';
import {useCurrentAccount} from '../SessionContext';
import {apiGet} from '../../api/client';
import type {Feature} from '../../api/preferences';

type Overrides=Partial<Record<Feature,boolean>>;
type Entry={key:string;projectId:string;value:Overrides;expires:number;requestedAt:number;generation:number;pending?:Promise<void>;listeners:Set<()=>void>};
const TTL=30_000;
const entries=new Map<string,Entry>();
let currentAccount:string|undefined;
let consumers=0;

function load(entry:Entry){
  if((entry.pending && entry.requestedAt+TTL>Date.now()) || entry.expires>Date.now())return;
  const generation=++entry.generation;
  entry.requestedAt=Date.now();
  // Consumers share this read-only request; one unmount must not abort it for others.
  const pending=apiGet<{features?:Overrides}>('/api/workbench/projects/'+encodeURIComponent(entry.projectId)).then(result=>{
    if(entries.get(entry.key)!==entry || entry.generation!==generation)return;
    entry.value=result.features||{};entry.expires=Date.now()+TTL;
    entry.listeners.forEach(notify=>notify());
  }).catch(()=>{
    // Keep the last known overrides on a transient failure; the next access can retry.
  }).finally(()=>{if(entry.pending===pending)entry.pending=undefined;});
  entry.pending=pending;
}

function relevant(entry:Entry,event:Event){
  const detail=(event as CustomEvent<{projectId?:string;project_id?:string;path?:string}>).detail;
  const projectId=detail?.projectId||detail?.project_id;
  if(projectId)return projectId===entry.projectId;
  if(!detail?.path)return true;
  const match=detail.path.match(/\/projects\/([^/?#]+)/);
  if(match)return match[1]===encodeURIComponent(entry.projectId)||match[1]===entry.projectId;
  return /\/preferences(?:\/|$)|\/workbench\/records(?:\/|$)/.test(detail.path);
}

function invalidate(event:Event){
  entries.forEach(entry=>{
    if(!relevant(entry,event))return;
    entry.expires=0;entry.generation++;entry.pending=undefined;
    if(entry.listeners.size)load(entry);
  });
}

function subscribe(){
  if(consumers++===0){
    window.addEventListener('atlas:data-change',invalidate);
    window.addEventListener('paperstride:records-change',invalidate);
  }
  return()=>{
    consumers--;
    if(consumers===0){
      window.removeEventListener('atlas:data-change',invalidate);
      window.removeEventListener('paperstride:records-change',invalidate);
      // Allow Strict Mode's immediate remount to reuse the request. Once there are
      // no consumers, discard cache entries so changes made elsewhere cannot be missed.
      queueMicrotask(()=>{if(consumers===0)entries.clear();});
    }
  };
}

/** Workspace, reader and inline actions reuse one account-scoped project read. */
export default function useProjectFeatures(projectId?:string){
  const {preferences}=usePreferences();
  const account=useCurrentAccount();
  const owner=account?'account:'+account.id:'local';
  const key=JSON.stringify([owner,projectId||'']);
  const [state,setState]=useState<{key:string;value:Overrides}>({key,value:{}});
  useEffect(()=>{
    if(currentAccount!==owner){entries.clear();currentAccount=owner;}
    if(!projectId)return;
    let entry=entries.get(key);
    if(!entry){entry={key,projectId,value:{},expires:0,requestedAt:0,generation:0,listeners:new Set()};entries.set(key,entry);}
    const selected=entry;
    const update=()=>setState({key,value:selected.value});
    selected.listeners.add(update);const unsubscribe=subscribe();update();load(selected);
    return()=>{selected.listeners.delete(update);unsubscribe();};
  },[owner,projectId,key]);
  const overrides=state.key===key?state.value:{};
  return Object.fromEntries(Object.entries(preferences.features).map(([k,v])=>[k,v&&overrides[k as Feature]!==false])) as Record<Feature,boolean>;
}

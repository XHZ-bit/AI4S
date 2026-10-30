import {StrictMode,type ReactNode} from 'react';
import {act,cleanup,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import useProjectFeatures from '../components/workbench/useProjectFeatures';
import {AccessModeProvider} from '../components/SessionContext';
import {apiGet} from '../api/client';

const preferences=vi.hoisted(()=>({features:{paper_guidance:true,coding:true,graph:true}}));
vi.mock('../components/PreferencesContext',()=>({usePreferences:()=>({preferences})}));
vi.mock('../api/client',()=>({apiGet:vi.fn()}));

function Probe({name,project='shared'}:{name:string;project?:string}){
  const features=useProjectFeatures(project);
  return <output data-testid={name}>{JSON.stringify(features)}</output>;
}
function User({id,children}:{id:string;children:ReactNode}){
  return <AccessModeProvider mode="multiuser" user={{id,username:id,role:'user'}}>{children}</AccessModeProvider>;
}
function deferred(){
  let resolve!:(value:any)=>void,reject!:(reason:unknown)=>void;
  const promise=new Promise<any>((yes,no)=>{resolve=yes;reject=no});
  return {promise,resolve,reject};
}
const value=(name:string)=>JSON.parse(screen.getByTestId(name).textContent!);
const changed=(name:string,detail:object)=>act(()=>window.dispatchEvent(new CustomEvent(name,{detail})));
beforeEach(()=>{vi.mocked(apiGet).mockReset();preferences.features={paper_guidance:true,coding:true,graph:true};});
afterEach(async()=>{cleanup();await Promise.resolve();vi.restoreAllMocks();});

test('three readers and Strict Mode share one GET; removing one cannot cancel the others',async()=>{
  const response=deferred();vi.mocked(apiGet).mockReturnValue(response.promise);
  const view=render(<StrictMode><User id="shared-account"><Probe name="workspace"/><Probe name="paper"/><Probe name="actions"/></User></StrictMode>);
  expect(apiGet).toHaveBeenCalledTimes(1);
  expect(apiGet).toHaveBeenCalledWith('/api/workbench/projects/shared');
  view.rerender(<StrictMode><User id="shared-account"><Probe name="paper"/><Probe name="actions"/></User></StrictMode>);
  await act(async()=>response.resolve({features:{paper_guidance:false,coding:false}}));
  expect(apiGet).toHaveBeenCalledTimes(1);
  expect(value('paper')).toEqual({paper_guidance:false,coding:false,graph:true});
  expect(value('actions')).toEqual(value('paper'));
});

test('a fresh cache serves new readers and an expired result refreshes all consumers once',async()=>{
  let now=1000;vi.spyOn(Date,'now').mockImplementation(()=>now);
  vi.mocked(apiGet).mockResolvedValueOnce({features:{coding:false}});
  const view=render(<User id="cache-account"><Probe name="one"/></User>);
  await act(async()=>{});
  view.rerender(<User id="cache-account"><Probe name="one"/><Probe name="two"/></User>);
  expect(apiGet).toHaveBeenCalledTimes(1);expect(value('two').coding).toBe(false);
  now+=30_001;const refreshed=deferred();vi.mocked(apiGet).mockReturnValueOnce(refreshed.promise);
  view.rerender(<User id="cache-account"><Probe name="one"/><Probe name="two"/><Probe name="three"/></User>);
  expect(apiGet).toHaveBeenCalledTimes(2);expect(value('three').coding).toBe(false);
  await act(async()=>refreshed.resolve({features:{coding:true}}));
  for(const name of ['one','two','three'])expect(value(name).coding).toBe(true);
});

test('account changes clear the visible overrides and reject old responses even when returning',async()=>{
  const first=deferred(),second=deferred(),returning=deferred();
  vi.mocked(apiGet).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(returning.promise);
  const view=render(<User id="private-one"><Probe name="reader"/></User>);
  view.rerender(<User id="private-two"><Probe name="reader"/></User>);
  await act(async()=>second.resolve({features:{graph:false}}));expect(value('reader').graph).toBe(false);
  await act(async()=>first.resolve({features:{coding:false}}));
  expect(value('reader')).toEqual({paper_guidance:true,coding:true,graph:false});
  view.rerender(<User id="private-one"><Probe name="reader"/></User>);
  expect(apiGet).toHaveBeenCalledTimes(3);expect(value('reader')).toEqual({paper_guidance:true,coding:true,graph:true});
  await act(async()=>returning.resolve({features:{paper_guidance:false}}));
  expect(value('reader')).toEqual({paper_guidance:false,coding:true,graph:true});
});

test('different projects remain isolated and scoped changes refresh only the affected project',async()=>{
  vi.mocked(apiGet).mockResolvedValueOnce({features:{coding:false}}).mockResolvedValueOnce({features:{graph:false}});
  render(<User id="project-account"><Probe name="one" project="one"/><Probe name="same" project="one"/><Probe name="two" project="two"/></User>);
  await act(async()=>{});expect(apiGet).toHaveBeenCalledTimes(2);
  const refresh=deferred();vi.mocked(apiGet).mockReturnValueOnce(refresh.promise);
  changed('atlas:data-change',{path:'/api/workbench/projects/one/preferences'});
  expect(apiGet).toHaveBeenCalledTimes(3);expect(apiGet).toHaveBeenLastCalledWith('/api/workbench/projects/one');
  changed('atlas:data-change',{path:'/api/papers/something/read-position'});
  changed('paperstride:records-change',{projectId:'unrelated'});
  expect(apiGet).toHaveBeenCalledTimes(3);
  await act(async()=>refresh.resolve({features:{coding:true}}));
  expect(value('one').coding).toBe(true);expect(value('same').coding).toBe(true);expect(value('two').graph).toBe(false);
  vi.mocked(apiGet).mockResolvedValueOnce({features:{paper_guidance:false}});
  changed('paperstride:records-change',{projectId:'two'});await act(async()=>{});
  expect(apiGet).toHaveBeenCalledTimes(4);expect(apiGet).toHaveBeenLastCalledWith('/api/workbench/projects/two');
  expect(value('two').paper_guidance).toBe(false);expect(value('one').paper_guidance).toBe(true);
});

test('invalidating an in-flight read discards its stale result and shares the replacement',async()=>{
  const old=deferred(),fresh=deferred();vi.mocked(apiGet).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
  render(<User id="invalidation-account"><Probe name="one"/><Probe name="two"/></User>);
  act(()=>window.dispatchEvent(new Event('atlas:data-change')));expect(apiGet).toHaveBeenCalledTimes(2);
  await act(async()=>fresh.resolve({features:{graph:false}}));
  await act(async()=>old.resolve({features:{coding:false}}));
  expect(value('one')).toEqual({paper_guidance:true,coding:true,graph:false});expect(value('two')).toEqual(value('one'));
});

test('an overdue in-flight request is replaced on new access and cannot overwrite the replacement',async()=>{
  let now=1000;vi.spyOn(Date,'now').mockImplementation(()=>now);
  const old=deferred(),fresh=deferred();vi.mocked(apiGet).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
  const view=render(<User id="overdue-account"><Probe name="one"/></User>);
  now+=30_001;view.rerender(<User id="overdue-account"><Probe name="one"/><Probe name="two"/></User>);
  expect(apiGet).toHaveBeenCalledTimes(2);
  await act(async()=>fresh.resolve({features:{graph:false}}));await act(async()=>old.resolve({features:{coding:false}}));
  expect(value('two')).toEqual({paper_guidance:true,coding:true,graph:false});expect(value('one')).toEqual(value('two'));
});

test('a failed refresh keeps known overrides and a later consumer can retry without paid work',async()=>{
  vi.mocked(apiGet).mockResolvedValueOnce({features:{coding:false}});
  const view=render(<User id="retry-account"><Probe name="one"/></User>);await act(async()=>{});
  vi.mocked(apiGet).mockRejectedValueOnce(new Error('offline'));
  changed('paperstride:records-change',{projectId:'shared'});await act(async()=>{});
  expect(value('one').coding).toBe(false);
  vi.mocked(apiGet).mockResolvedValueOnce({features:{coding:true}});
  view.rerender(<User id="retry-account"><Probe name="one"/><Probe name="two"/></User>);await act(async()=>{});
  expect(value('one').coding).toBe(true);expect(value('two').coding).toBe(true);
  expect(apiGet).toHaveBeenCalledTimes(3);
  expect(vi.mocked(apiGet).mock.calls.every(([path])=>path==='/api/workbench/projects/shared')).toBe(true);
});

test('project configuration cannot enable globally disabled learning',async()=>{
  preferences.features.coding=false;vi.mocked(apiGet).mockResolvedValue({features:{coding:true,paper_guidance:false}});
  render(<User id="global-account"><Probe name="reader"/></User>);await act(async()=>{});
  expect(value('reader')).toEqual({paper_guidance:false,coding:false,graph:true});
});

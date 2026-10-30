import {act,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import useRecentProjects from '../components/workbench/useRecentProjects';
import {AccessModeProvider} from '../components/SessionContext';
import {listProjects} from '../api/projects';
vi.mock('../api/projects',()=>({listProjects:vi.fn()}));
function Probe({name}:{name:string}){const state=useRecentProjects();return <div data-testid={name}>{state.items.map(p=>p.title).join(',')}</div>}
function User({id,children}:{id:string;children:React.ReactNode}){return <AccessModeProvider mode="multiuser" user={{id,username:id,role:'user'}}>{children}</AccessModeProvider>}
beforeEach(()=>vi.mocked(listProjects).mockReset());
test('the sidebar and workbench share an in-flight account request',async()=>{
 let finish!:(value:any)=>void;vi.mocked(listProjects).mockReturnValue(new Promise(done=>{finish=done}));
 render(<User id="same-account"><Probe name="shell"/><Probe name="home"/></User>);expect(listProjects).toHaveBeenCalledTimes(1);
 await act(async()=>finish({items:[{id:'p',title:'My space',updated_at:'2026-10-25'}]}));
 expect(screen.getByTestId('shell').textContent).toBe('My space');expect(screen.getByTestId('home').textContent).toBe('My space');
});
test('switching account clears the old view and an older response cannot fill the new account',async()=>{
 let old!:(value:any)=>void,newer!:(value:any)=>void;
 vi.mocked(listProjects).mockReturnValueOnce(new Promise(done=>{old=done})).mockReturnValueOnce(new Promise(done=>{newer=done}));
 const view=render(<User id="first-account"><Probe name="view"/></User>);view.rerender(<User id="second-account"><Probe name="view"/></User>);
 await act(async()=>old({items:[{id:'private',title:'First account private',updated_at:'2026-10-25'}]}));expect(screen.getByTestId('view').textContent).toBe('');
 await act(async()=>newer({items:[{id:'second',title:'Second space',updated_at:'2026-10-25'}]}));await waitFor(()=>expect(screen.getByTestId('view').textContent).toBe('Second space'));
});

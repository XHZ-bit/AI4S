import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import TopicExplorer from '../components/workbench/TopicExplorer';
const api=vi.hoisted(()=>({apiGet:vi.fn(),apiPost:vi.fn()}));
vi.mock('../api/client',()=>api);
const result=(interest:string)=>({brief:{interests:interest,background:'',resources:''},directions:[{id:'first',title:'探索一个使用场景',question:interest+'在什么情况下遇到困难？',why:'从场景开始',first_step:'先查阅来源',needed:'资源未知',paper_uids:[]}],papers:[],notice:'探索切口',search_url:'/manage'});
beforeEach(()=>{api.apiPost.mockReset();api.apiGet.mockReset()});
test('stale topic responses cannot be adopted under a different brief',async()=>{
 let resolve!:(v:ReturnType<typeof result>)=>void;api.apiPost.mockReturnValue(new Promise(done=>{resolve=done}));
 const choose=vi.fn();render(<MemoryRouter><TopicExplorer onChoose={choose}/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('探索兴趣'),{target:{value:'兴趣 A'}});fireEvent.click(screen.getByRole('button',{name:'帮我展开几个可探索的方向'}));
 fireEvent.change(screen.getByLabelText('探索兴趣'),{target:{value:'兴趣 B'}});
 await act(async()=>resolve(result('兴趣 A')));
 expect(await screen.findByText('输入已改变，请重新展开方向。')).toBeTruthy();expect(screen.queryByRole('button',{name:'以此为起点，继续修改'})).toBeNull();expect(choose).not.toHaveBeenCalled();
});
test('adopting a direction uses the generated brief and editing clears old directions',async()=>{
 api.apiPost.mockResolvedValue(result('课堂参与'));
 const choose=vi.fn();render(<MemoryRouter><TopicExplorer onChoose={choose}/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('探索兴趣'),{target:{value:'课堂参与'}});fireEvent.click(screen.getByRole('button',{name:'帮我展开几个可探索的方向'}));
 fireEvent.click(await screen.findByRole('button',{name:'以此为起点，继续修改'}));expect(choose).toHaveBeenCalledWith(expect.objectContaining({id:'first'}),{interests:'课堂参与',background:'',resources:''});
 fireEvent.change(screen.getByLabelText('探索兴趣'),{target:{value:'新的方向'}});await waitFor(()=>expect(screen.queryByText('探索一个使用场景')).toBeNull());
 expect(api.apiPost).toHaveBeenCalledTimes(1);
});

import {useEffect,useState} from 'react';
import {Alert,Button,Select,Space} from 'antd';
import {Link,useSearchParams} from 'react-router-dom';
import {apiGet} from '../../api/client';
import {PaperDetailContent} from '../../pages/PaperDetail';
import {contextLink,safeReturnTo} from '../../api/workContext';
import {usePreferences} from '../PreferencesContext';
export default function ProjectReading({projectId,workspace}:{projectId:string;workspace?:any}){
 const [params,setParams]=useSearchParams();const [data,setData]=useState<any>(workspace),[error,setError]=useState('');const {preferences}=usePreferences();
 useEffect(()=>{if(workspace){setData(workspace);return}let live=true;void apiGet<any>('/api/workbench/projects/'+projectId).then(r=>{if(live)setData(r)}).catch(e=>{if(live)setError(String(e))});return()=>{live=false}},[projectId,workspace]);
 const uid=params.get('paper')||data?.papers[0]?.uid;const returnTo=safeReturnTo(params.get('returnTo'));

 if(error)return <Alert type="error" message={error}/>;
 return <section>{returnTo&&<Link className="learning-return" to={returnTo}>返回刚才的工作</Link>}<Space wrap className="ps-project-reader-tools"><Select aria-label="当前论文" showSearch optionFilterProp="label" value={uid} style={{width:420,maxWidth:'100%'}} placeholder="选择关联论文" options={(data?.papers||[]).map((p:any)=>({value:p.uid,label:p.title}))} onChange={value=>setParams(old=>{const n=new URLSearchParams(old);n.set('paper',value);n.set('project',projectId);['page','ref','focus','document_id','document_version','session','step','lesson','activity','unit','returnTo'].forEach(key=>n.delete(key));n.set('panel','closed');return n})}/><Link to={`/manage?project=${projectId}`}>添加资料</Link>{uid&&<><Link to={contextLink(`/papers/${uid}?tab=reading`,params,{project:projectId,paper:uid})}>独立打开</Link>{preferences.features.paper_guidance&&data?.features.paper_guidance!==false&&<Button onClick={()=>setParams(old=>{const n=new URLSearchParams(old);n.set('panel','tutor');n.set('paper',uid);n.set('project',projectId);return n})}>随文辅导</Button>}</>}</Space>{uid?<><PaperDetailContent key={uid} paperUid={uid} embedded/></>:<p>添加论文后，可以在这里阅读、做笔记并提问。</p>}</section>;
}

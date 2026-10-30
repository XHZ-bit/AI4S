import useProjectFeatures from './useProjectFeatures';
import {useRef,useState} from 'react';
import {Button} from 'antd';
import {useSearchParams,useParams} from 'react-router-dom';
import {useInspector} from '../workspace/InspectorContext';
import type {SourceSelection} from '../../api/workContext';
import Notebook from './Notebook';
export default function ReadingActions({uid,documentId,documentVersion,children}:{uid:string;documentId?:string;documentVersion?:string;children:React.ReactNode}){
 const [params]=useSearchParams(),route=useParams();const projectId=params.get('project')||route.projectId;
 const features=useProjectFeatures(projectId),inspector=useInspector(),host=useRef<HTMLDivElement>(null);
 const [selection,setSelection]=useState<SourceSelection>(),[fallback,setFallback]=useState(false),[position,setPosition]=useState({top:0,left:0});
 function capture(){const sel=window.getSelection();if(!sel||sel.isCollapsed||!host.current?.contains(sel.anchorNode)||!host.current?.contains(sel.focusNode))return;const text=sel.toString().trim();const anchor=sel.anchorNode?.parentElement;if(!anchor?.closest('.textLayer')||!text||text.length>8000)return;const page=Number(anchor.closest('[data-pdf-page]')?.getAttribute('data-pdf-page')||params.get('page')||1);const rect=sel.getRangeAt(0).getBoundingClientRect(),outer=host.current.getBoundingClientRect();setPosition({top:Math.max(0,rect.bottom-outer.top+8),left:Math.max(0,Math.min(rect.left-outer.left,outer.width-300))});setSelection({paper_uid:uid,document_id:documentId,document_version:documentVersion,page,quote:text});}
 function open(panel:'tutor'|'notes',kind?:'note'|'question'){if(!selection)return;if(inspector.openSelection){inspector.openSelection({...selection,kind},panel);setSelection(undefined);}else setFallback(true);}
 return <div className="ps-reading-actions" ref={host} onMouseUp={capture} onKeyUp={e=>{if(e.key==='Shift'||e.key.startsWith('Arrow'))capture()}}>{children}{selection&&<div className="ps-selection-tools" style={position} role="toolbar" aria-label="选文操作" onMouseDown={e=>e.preventDefault()}>{features.paper_guidance&&<Button size="small" onClick={()=>open('tutor')}>解释</Button>}<Button size="small" onClick={()=>open('notes','note')}>记笔记</Button><Button size="small" onClick={()=>open('notes','question')}>存为问题</Button><Button size="small" type="text" aria-label="关闭选文操作" onClick={()=>setSelection(undefined)}>收起</Button></div>}{fallback&&selection&&<Notebook compact projectId={projectId} paperUid={uid} initialDraft={selection}/>}</div>;
}

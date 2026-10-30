import {useState,type ReactNode} from 'react';

/** Closed secondary views do not mount or start their requests. */
export default function DeferredSection({title,initialOpen=false,children}:{title:string;initialOpen?:boolean;children:ReactNode}) {
  const [open,setOpen]=useState(initialOpen);
  return <details open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>{title}</summary>{open&&children}</details>;
}

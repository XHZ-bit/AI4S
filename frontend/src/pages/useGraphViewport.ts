import {useLayoutEffect,useRef,useState} from 'react';

/** Keep the rendered canvas and its scrollable side panes within the visible workspace. */
export function useGraphViewport(layoutKey:string){
 const explorer=useRef<HTMLElement>(null),workspace=useRef<HTMLDivElement>(null),stage=useRef<HTMLDivElement>(null),optionsMenu=useRef<HTMLDetailsElement>(null);
 const [size,setSize]=useState({width:800,height:480,optionsHeight:440});
 useLayoutEffect(()=>{
  const area=workspace.current;
  if(!area)return;
  let frame=0;
  const measure=()=>{
   frame=0;
   const bounds=area.getBoundingClientRect();
   const canvasBounds=stage.current?.getBoundingClientRect();
   const viewport=window.visualViewport;
   let bottom=viewport?viewport.offsetTop+viewport.height:window.innerHeight;
   const navigation=document.querySelector('.atlas-mobile-navigation')?.getBoundingClientRect();
   if(navigation&&navigation.height>0&&navigation.top>0)bottom=Math.min(bottom,navigation.top);
   const width=Math.max(1,Math.floor(canvasBounds&&canvasBounds.width>0?canvasBounds.width:bounds.width));
   const height=Math.max(220,Math.floor(bottom-Math.max(0,bounds.top)-16));
   const optionsHeight=Math.max(96,Math.floor(bottom-(optionsMenu.current?.getBoundingClientRect().bottom||bounds.top)-24));
   setSize(current=>current.width===width&&current.height===height&&current.optionsHeight===optionsHeight?current:{width,height,optionsHeight});
  };
  const schedule=()=>{if(!frame)frame=window.requestAnimationFrame(measure)};
  const observer=new ResizeObserver(schedule);
  // Ancestors detect controls opening above the graph. A stable state check stops resize feedback.
  const targets=[area,stage.current,optionsMenu.current,explorer.current,explorer.current?.parentElement];
  [...new Set(targets)].forEach(element=>{if(element)observer.observe(element)});
  window.addEventListener('resize',schedule);
  window.visualViewport?.addEventListener('resize',schedule);
  measure();
  return()=>{observer.disconnect();window.cancelAnimationFrame(frame);window.removeEventListener('resize',schedule);window.visualViewport?.removeEventListener('resize',schedule)};
 },[layoutKey]);
 return {explorer,workspace,stage,optionsMenu,...size};
}

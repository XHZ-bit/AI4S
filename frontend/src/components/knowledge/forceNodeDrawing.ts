/** Selection changes the filled node itself. It never paints an outline or halo. */
export function canvasTooltip(text:string){
 const entities:Record<string,string>={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
 return text.replace(/[&<>"']/g,character=>entities[character]);
}

export function brightenNodeColor(color:string,amount=.38){
 const match=/^#([0-9a-f]{6})$/i.exec(color);
 if(!match)return color;
 const parts=[0,2,4].map(offset=>parseInt(match[1].slice(offset,offset+2),16));
 return '#'+parts.map(value=>Math.round(value+(255-value)*amount).toString(16).padStart(2,'0')).join('');
}

export function drawForceNode(ctx:CanvasRenderingContext2D,node:{x?:number;y?:number},color:string,radius:number,selected:boolean,dimmed=false){
 if(!Number.isFinite(node.x)||!Number.isFinite(node.y))return;
 ctx.save();ctx.shadowBlur=0;ctx.globalAlpha=dimmed?.46:1;
 ctx.beginPath();ctx.arc(node.x!,node.y!,selected?radius*1.45:radius,0,Math.PI*2);
 ctx.fillStyle=selected?brightenNodeColor(color):color;ctx.fill();ctx.restore();
}

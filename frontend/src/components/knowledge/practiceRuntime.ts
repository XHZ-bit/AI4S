export interface BrowserPythonResult {
 status:'success'|'error'|'timeout'|'cancelled';output:string;elapsed_ms:number;passed:boolean|null;
}
export interface PythonCallbacks {
 onState:(state:'loading'|'running')=>void;onOutput:(output:string)=>void;onComplete:(result:BrowserPythonResult)=>void;
}
/** The host only creates an opaque iframe. User Python never runs on its origin. */
export function runBrowserPython(code:string,inputs:unknown,tests:string,callbacks:PythonCallbacks,
 timeouts:{loading?:number;execution?:number}={}) {
 const started=performance.now(),channel=crypto.randomUUID(),abort=new AbortController();
 let frame:HTMLIFrameElement|undefined,timer:ReturnType<typeof setTimeout>|undefined,done=false,executing=false;
 let receivedMessages=0;
 let output='';
 const cleanup=()=>{
  clearTimeout(timer);abort.abort();window.removeEventListener('message',receive);
  const current=frame;frame=undefined;
  // Give the iframe's main thread a chance to terminate the busy worker before
  // removing its browsing context; pagehide is a second termination path.
  current?.contentWindow?.postMessage({channel,type:'stop'},'*');
  if(current)setTimeout(()=>current.remove(),100);
 };
 const finish=(status:BrowserPythonResult['status'],text:string,passed:boolean|null=null)=>{
  if(done)return;done=true;cleanup();callbacks.onComplete({status,output:text.slice(-20000),passed,elapsed_ms:Math.round(performance.now()-started)});
 };
 function receive(event:MessageEvent){
  if(!frame||event.source!==frame.contentWindow||event.data?.channel!==channel||done)return;
  if(++receivedMessages>1000){finish('error','工作线程消息过多，已停止运行。请减少重复输出。');return}
  const message=event.data;
  if(message.type==='ready'){
   if(executing)return; // Untrusted Python cannot reset its execution deadline.
   executing=true;
   clearTimeout(timer);callbacks.onState('running');
   timer=setTimeout(()=>finish('timeout',(output?output+'\n':'')+'运行超过 5 秒，工作线程已停止。请检查无限循环或减少输入。'),timeouts.execution??5000);
   frame.contentWindow?.postMessage({channel,type:'execute',code,inputs,tests},'*');
  }else if(message.type==='output'&&typeof message.output==='string'){
   output=message.output.slice(-20000);callbacks.onOutput(output);
  }else if(message.type==='result'){
   finish(message.status==='success'?'success':'error',String(message.output??''),typeof message.passed==='boolean'?message.passed:null);
  }else if(message.type==='fatal')finish('error',String(message.output??'Python 运行环境未能启动，请重试。'));
 }
 callbacks.onState('loading');
 timer=setTimeout(()=>finish('timeout','本地 Python 环境加载超时。请检查本机运行文件并重试。'),timeouts.loading??45000);
 window.addEventListener('message',receive);
 void fetch('/knowledge-practice-worker.js',{credentials:'omit',signal:abort.signal}).then(response=>{
  if(!response.ok)throw new Error(`运行脚本读取失败（${response.status}）`);return response.text();
 }).then(source=>{
  if(done)return;
  const runtimeBase=new URL('/python-runtime/',window.location.href).href;
  const csp=`default-src 'none'; script-src 'nonce-${channel}' 'unsafe-eval' 'wasm-unsafe-eval' data: ${runtimeBase}; worker-src data:; connect-src ${runtimeBase}; img-src 'none'; style-src 'none'; form-action 'none'; base-uri 'none'`;
  const workerSource=JSON.stringify(`const RUNTIME_BASE=${JSON.stringify(runtimeBase)};\n${source}`).replace(/</g,'\\u003c');
  frame=document.createElement('iframe');frame.hidden=true;frame.title='隔离的节点 Python 练习';frame.setAttribute('sandbox','allow-scripts');
  frame.srcdoc=`<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="${csp}"><meta charset="utf-8"></head><body><script nonce="${channel}">
const channel=${JSON.stringify(channel)};
const worker=new Worker('data:text/javascript;charset=utf-8,'+encodeURIComponent(${workerSource}),{type:'module',credentials:'omit'});
worker.onmessage=event=>parent.postMessage({...event.data,channel},'*');
worker.onerror=event=>parent.postMessage({channel,type:'fatal',output:'Python 工作线程启动失败：'+event.message},'*');
window.addEventListener('message',event=>{if(event.source!==parent||event.data?.channel!==channel)return;if(event.data.type==='stop'){worker.terminate();return;}if(event.data.type==='execute')worker.postMessage(event.data);});
window.addEventListener('pagehide',()=>worker.terminate());
</script></body></html>`;
  document.body.appendChild(frame);
 }).catch(error=>{if(!done)finish('error','Python 环境未能启动：'+String(error)+'。可重试运行，代码已保留。')});
 return {cancel:()=>finish('cancelled',(output?output+'\n':'')+'已停止工作线程，代码与输入已保留。')};
}

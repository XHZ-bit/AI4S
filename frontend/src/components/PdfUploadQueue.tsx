import { useEffect, useRef, useState } from "react";
import { Alert, Button, Progress, Space, Tag } from "antd";
import { CheckCircleOutlined, CloudUploadOutlined, FilePdfOutlined, InfoCircleOutlined, PauseOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import { getUploadTask, reparsePaper, uploadPdf, type UploadFailure } from "../api/papers";
import "./pdf-upload-queue.css";

type State = "waiting" | "validating" | "uploading" | "processing" | "saved" | "done" | "failed" | "uncertain" | "cancelled";
type Item = { id: number; file: File; state: State; uid?: string; taskId?: number; detail?: string; retryable?: boolean; linked?: boolean; linking?: boolean; linkError?: string };
const MAX_FILES = 20;
const labels: Record<State, string> = { waiting: "等待上传", validating: "检查文件", uploading: "正在上传", processing: "已保存 · 解析中", saved: "原文已保存 · 等待排队", done: "解析完成", failed: "失败", uncertain: "结果待确认", cancelled: "已从本地队列取消" };

function aborted() { return new DOMException("Queue stopped", "AbortError"); }
function wait(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(aborted()); return; }
    const stop = () => { clearTimeout(timer); reject(aborted()); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
    signal.addEventListener("abort", stop, { once: true });
  });
}
function visible(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(aborted()); return; }
    if (!document.hidden) { resolve(); return; }
    const clean = () => { document.removeEventListener("visibilitychange", changed); signal.removeEventListener("abort", stop); };
    const changed = () => { if (!document.hidden) { clean(); resolve(); } };
    const stop = () => { clean(); reject(aborted()); };
    document.addEventListener("visibilitychange", changed); signal.addEventListener("abort", stop, { once: true });
  });
}

export default function PdfUploadQueue({ maxFileBytes, onLibraryChange, projectId }: { projectId?:string; maxFileBytes?: number; onLibraryChange: () => void }) {
  const [items, setItems] = useState<Item[]>([]), [paused, setPaused] = useState(false), [notice, setNotice] = useState("");
  const [dragging, setDragging] = useState(false), dragDepth = useRef(0);
  const queue = useRef<Item[]>([]), sequence = useRef(0), running = useRef(false), alive = useRef(true), pausedRef = useRef(false);
  const active = useRef<AbortController>(), input = useRef<HTMLInputElement>(null), limit = useRef<number>(), checkedLimit = useRef(false);
  const changed = useRef(onLibraryChange); changed.current = onLibraryChange;
  if (maxFileBytes && Number.isFinite(maxFileBytes) && maxFileBytes > 0) { limit.current = maxFileBytes; checkedLimit.current = true; }
  useEffect(() => { alive.current = true; return () => { alive.current = false; active.current?.abort(); }; }, []);

  function replace(next: Item[]) { queue.current = next; if (alive.current) setItems(next); }
  function update(id: number, patch: Partial<Item>) { replace(queue.current.map(item => item.id === id ? { ...item, ...patch } : item)); }
  async function linkToProject(id:number,uid:string,signal?:AbortSignal) {
    if(!projectId)return;
    update(id,{linking:true,linkError:undefined});
    try {const result=await apiPost<{linked:boolean}>(`/api/workbench/projects/${encodeURIComponent(projectId)}/papers`,{paper_uid:uid},signal);if(!result.linked)throw new Error("未收到关联确认");if(alive.current)update(id,{linked:true});}
    catch(e){if(alive.current&&!signal?.aborted)update(id,{linkError:`文件已保存，加入研究空间失败：${String(e)}`});}
    finally{if(alive.current)update(id,{linking:false});}
  }
  function pause(value: boolean) { pausedRef.current = value; if (alive.current) setPaused(value); }

  async function readLimit(signal: AbortSignal) {
    if (checkedLimit.current) return;
    checkedLimit.current = true;
    try {
      const result = await apiGet<{ limits?: { pdf_max_bytes?: number } }>("/api/system/status", undefined, signal);
      if (signal.aborted) throw aborted();
      const bytes = result.limits?.pdf_max_bytes;
      if (typeof bytes === "number" && Number.isFinite(bytes) && bytes > 0) limit.current = bytes;
      else setNotice("无法预检文件大小，上传仍由服务器校验实际限制。");
    } catch (error) {
      if (signal.aborted) throw error;
      setNotice("无法预检文件大小，上传仍由服务器校验实际限制。");
    }
  }

  async function poll(item: Item, signal: AbortSignal) {
    let attempts = 0;
    while (!signal.aborted) {
      await visible(signal);
      const task = await getUploadTask(item.taskId!, signal);
      if (signal.aborted) throw aborted();
      if (task.status === "done") {
        update(item.id, { state: "done", detail: task.result?.warnings?.length ? "已完成，有处理提示，可在处理进度查看。" : "解析已完成，可以开始阅读。" });
        changed.current(); return;
      }
      if (["failed", "cancelled", "interrupted"].includes(task.status)) {
        update(item.id, { state: "failed", retryable: true, detail: `原文已保存；解析${task.status === "cancelled" ? "已取消" : task.status === "interrupted" ? "已中断" : "失败"}。${task.error || "可只重试解析。"}` });
        changed.current(); return;
      }
      if (task.status !== "queued" && task.status !== "running") throw new Error("任务状态无法确认");
      await wait(Math.min(15000, 1000 * 2 ** Math.min(attempts++, 4)), signal);
    }
    throw aborted();
  }

  async function run() {
    if (!alive.current || running.current || pausedRef.current) return;
    running.current = true;
    try {
      while (alive.current && !pausedRef.current) {
        if (queue.current.some(entry => entry.state === "uncertain" || entry.state === "saved")) { pause(true); break; }
        const item = queue.current.find(entry => entry.state === "processing") || queue.current.find(entry => entry.state === "waiting");
        if (!item) break;
        const controller = new AbortController(); active.current = controller;
        let accepted: Item | undefined = item.state === "processing" ? item : undefined;
        try {
          if (!accepted) {
            if (!/\.pdf$/i.test(item.file.name) || item.file.size === 0) {
              update(item.id, { state: "failed", retryable: false, detail: "请选择非空的 PDF 文件；此文件未提交。" }); continue;
            }
            update(item.id, { state: "validating", detail: undefined });
            await readLimit(controller.signal);
            if (!alive.current || controller.signal.aborted) throw aborted();
            if (!item.uid && limit.current && item.file.size > limit.current) {
              update(item.id, { state: "failed", retryable: false, detail: `文件超过当前单份大小上限（${(limit.current / 1024 ** 2).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} MB），未提交。` }); continue;
            }
            update(item.id, { state: "uploading", detail: item.uid ? "正在为已保存原文重新提交解析…" : "正在发送文件，尚未确认服务器接收。" });
            const receipt = item.uid ? { uid: item.uid, ...await reparsePaper(item.uid, controller.signal) } : await uploadPdf(item.file, controller.signal);
            if (!alive.current || controller.signal.aborted) throw aborted();
            if (receipt && typeof receipt.uid === "string") {
              update(item.id, { uid: receipt.uid });
              if(projectId)await linkToProject(item.id,receipt.uid,controller.signal);
            }
            if (receipt && Number.isInteger(receipt.task_id) && receipt.task_id > 0) {
              accepted = { ...item, uid: receipt.uid || item.uid, taskId: receipt.task_id, state: "processing" };
              update(item.id, { taskId: receipt.task_id, state: "processing" });
            }
            if (!receipt || typeof receipt.uid !== "string" || !Number.isInteger(receipt.task_id) || receipt.task_id <= 0) throw new Error("服务器未返回可确认的论文和任务编号");
            accepted = { ...item, uid: receipt.uid, taskId: receipt.task_id, state: "processing" };
            update(item.id, { state: "processing", uid: receipt.uid, taskId: receipt.task_id, detail: "原文已保存，等待解析任务结束后再提交下一份。" });
            changed.current();
          }
          await poll(accepted, controller.signal);
        } catch (error) {
          if (!alive.current || controller.signal.aborted) return;
          const text = error instanceof Error ? error.message : String(error);
          if (accepted) {
            update(item.id, { state: "processing", detail: `原文已保存，任务结果暂无法确认：${text}。恢复队列时将先查询此任务。` }); pause(true);
          } else {
            const failure = error as UploadFailure;
            const status = failure?.status;
            const savedUid = failure?.saved && failure.uid || item.uid;
            if (savedUid && status === 429) {
              update(item.id, { state: "saved", uid: savedUid, retryable: true, detail: `原文已保存，尚未排入解析：${text}。继续队列会只重新排队解析，不会重传 PDF。` });
              if(projectId)await linkToProject(item.id,savedUid,controller.signal);
              changed.current(); pause(true); continue;
            }
            const uncertain = status === undefined || status === 429 || status >= 500;
            update(item.id, { state: uncertain ? "uncertain" : "failed", retryable: true,
              detail: uncertain ? `文件可能已保存：${text}。请先查看处理进度或论文库，确认后重试此文件。` : `服务器拒绝本次提交：${text}` });
            if (uncertain || status === 401 || status === 403) pause(true);
          }
        } finally { if (active.current === controller) active.current = undefined; }
      }
    } finally { running.current = false; }
  }

  function add(files: File[]) {
    const room = MAX_FILES - queue.current.length;
    if (files.length > room) setNotice(`本地队列最多保留 ${MAX_FILES} 份，只加入前 ${Math.max(0, room)} 份；可清理已结束记录后继续添加。`);
    replace([...queue.current, ...files.slice(0, Math.max(0, room)).map(file => ({ id: ++sequence.current, file, state: "waiting" as const }))]);
    void run();
  }
  function resume() {
    if (queue.current.some(item => item.state === "uncertain")) { setNotice("请先确认结果待确认项：可查看服务器记录、手动重试该文件，或从本地队列取消后再继续。"); return; }
    replace(queue.current.map(item => item.state === "saved" ? { ...item, state: "waiting", detail: undefined } : item));
    pause(false); void run();
  }
  function retry(ids: number[]) {
    replace(queue.current.map(item => ids.includes(item.id) ? { ...item, state: "waiting", detail: undefined } : item));
    if (!queue.current.some(item => item.state === "uncertain" || item.state === "saved")) pause(false);
    void run();
  }
  const failed = items.filter(item => item.state === "failed" && item.retryable);
  const hasPending = items.some(item => ["waiting", "validating", "uploading", "processing", "saved", "uncertain"].includes(item.state));
  const completed = items.filter(item => item.state === "done").length;
  const errors = items.filter(item => item.state === "failed" || item.state === "uncertain").length;
  const fileSize = (bytes: number) => bytes < 1024 ** 2 ? `${Math.max(1, Math.ceil(bytes / 1024))} KB` : `${(bytes / 1024 ** 2).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} MB`;
  return <section className="atlas-upload-queue" aria-label="PDF 上传队列">
    <input ref={input} className="atlas-upload-native-input" type="file" accept=".pdf,application/pdf" multiple aria-label="选择 PDF 文件"
      onChange={event => { add(Array.from(event.target.files || [])); event.target.value = ""; }} />
    <div className={`atlas-upload-dropzone${dragging ? " is-dragging" : ""}`}
      onDragEnter={event => { event.preventDefault(); dragDepth.current++; setDragging(true); }}
      onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
      onDragLeave={event => { event.preventDefault(); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }}
      onDrop={event => { event.preventDefault(); dragDepth.current = 0; setDragging(false); add(Array.from(event.dataTransfer.files || [])); }}>
      <button type="button" className="atlas-upload-drop-trigger" aria-label="上传 PDF" onClick={() => input.current?.click()}>
        <span className="atlas-upload-drop-icon"><CloudUploadOutlined aria-hidden="true" /></span>
        <span className="atlas-upload-drop-copy"><strong>{dragging ? "松开以加入上传队列" : "拖拽 PDF 到这里，或点击选择"}</strong><span>支持多选 · 原文先保存，再逐份解析</span></span>
        <span className="atlas-upload-choose">上传 PDF</span>
      </button>
    </div>
    <div className="atlas-upload-steps" aria-label="资料导入步骤"><span><i>1</i>选择 PDF</span><b aria-hidden="true">—</b><span><i>2</i>保存原文</span><b aria-hidden="true">—</b><span><i>3</i>解析后阅读</span></div>
    {!!items.length && <div className="atlas-upload-summary">
      <div className="atlas-upload-summary-copy" role="status" aria-live="polite"><strong>本地队列 {items.length} 份 · 解析完成 {completed} 份</strong><span>{paused ? "后续已暂停" : hasPending ? "按顺序处理" : "本轮处理已结束"}{errors ? ` · ${errors} 份需留意` : ""}</span></div>
      <Progress className="atlas-upload-progress" percent={Math.round(completed / items.length * 100)} showInfo={false} strokeColor="#0F766E" trailColor="#E8EFED" aria-label="队列解析完成比例" />
      <Space wrap className="atlas-upload-batch-actions">{paused ? <Button size="small" type="primary" icon={<PlayCircleOutlined aria-hidden="true" />} onClick={resume}>继续队列</Button> : <Button size="small" icon={<PauseOutlined aria-hidden="true" />} disabled={!hasPending} onClick={() => pause(true)}>暂停后续</Button>}
        <Button size="small" icon={<ReloadOutlined aria-hidden="true" />} disabled={!failed.length} onClick={() => retry(failed.map(item => item.id))}>重试失败项</Button>
        <Button size="small" type="text" disabled={!items.some(item => ["done", "failed", "cancelled"].includes(item.state))} onClick={() => replace(queue.current.filter(item => !["done", "failed", "cancelled"].includes(item.state)))}>清理已结束记录</Button>
      </Space>
    </div>}
    {notice && <Alert className="atlas-upload-feedback" type="info" showIcon message={notice} />}
    <ul className="atlas-upload-files">{items.map(item => <li key={item.id} className={`atlas-upload-file state-${item.state}`}>
      <span className="atlas-upload-file-icon">{item.state === "done" ? <CheckCircleOutlined aria-hidden="true" /> : <FilePdfOutlined aria-hidden="true" />}</span>
      <div className="atlas-upload-file-body"><div className="atlas-upload-file-heading"><strong title={item.file.name}>{item.file.name}</strong><span>{fileSize(item.file.size)}</span></div>
        <div className="atlas-upload-file-status"><Tag color={item.state === "done" ? "green" : item.state === "failed" || item.state === "uncertain" ? "orange" : undefined}>{labels[item.state]}</Tag>{item.detail && <p>{item.detail}</p>}</div>
        {item.linkError&&<p role="alert">{item.linkError}</p>}
        <Space wrap className="atlas-upload-file-actions">
          {item.uid && <Link className={item.state === "done" ? "atlas-upload-read" : ""} to={projectId&&item.linked?`/research/${encodeURIComponent(projectId)}?tab=reading&paper=${encodeURIComponent(item.uid)}`:`/papers/${encodeURIComponent(item.uid)}?tab=reading${projectId?`&project=${encodeURIComponent(projectId)}`:""}`}>{item.state === "done" ? "开始阅读" : "打开已保存论文"}</Link>}
          {projectId&&item.uid&&(item.linked?<span role="status">已加入研究空间</span>:<Button size="small" loading={item.linking} onClick={async()=>{await linkToProject(item.id,item.uid!);changed.current()}}>重试加入研究空间</Button>)}
          {item.taskId && <Link to="/tasks">查看任务 #{item.taskId}</Link>}
          {item.state === "waiting" && <Button type="text" size="small" onClick={() => update(item.id, { state: "cancelled", detail: "仅取消本地待提交项，未撤销服务器任务。" })}>取消此待上传项</Button>}
          {(item.state === "uncertain" || item.state === "saved" || item.state === "failed" && item.retryable) && <Button size="small" onClick={() => retry([item.id])}>{item.state === "uncertain" ? "确认后重试此文件" : item.uid ? "重试此解析" : "重试此文件"}</Button>}
          {item.state === "uncertain" && <Button type="text" size="small" onClick={() => update(item.id, { state: "cancelled", detail: "已从本地队列移除；服务器保存和处理状态请在论文库核对。" })}>从本地队列移除</Button>}
        </Space>
      </div>
    </li>)}</ul>
    <p className="atlas-upload-note"><InfoCircleOutlined aria-hidden="true" /><span>最多保留 {MAX_FILES} 份。暂停只停止后续提交；离开页面会停止本地队列，已提交的服务器任务继续处理。</span></p>
  </section>;
}

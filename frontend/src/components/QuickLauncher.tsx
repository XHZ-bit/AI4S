import {getUnifiedGraph} from "../api/unifiedGraph";
import {apiGet} from "../api/client";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Alert, Button, Input, Modal, type InputRef } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";
import { quickFindPapers, type QuickPaper } from "../api/quickFind";
import "./quick-launcher.css";
import {usePreferences} from "./PreferencesContext";

type Entry = { key: string; title: string; path: string; detail: string; keywords?: string };
const destinations: Entry[] = [
  {key:"graph",title:"知识图谱",path:"/graph",detail:"查找知识、关系与原文依据",keywords:"graph knowledge 方法 概念 公式"},
  { key: "home", title: "开始 / 继续", path: "/", detail: "回到首页", keywords: "home" },
  { key: "papers", title: "论文库", path: "/manage", detail: "导入和查找资料", keywords: "papers library upload pdf 上传" },
  { key: "starred", title: "收藏论文", path: "/manage?filter=starred", detail: "打开个人收藏", keywords: "favorites starred" },
  { key: "later", title: "稍后阅读", path: "/manage?filter=read_later", detail: "找回待阅读资料", keywords: "read later" },
  { key: "projects", title: "科研课题", path: "/research", detail: "课题、证据与方案", keywords: "projects research" },
  { key: "workflow", title: "任务面板", path: "/workflow", detail: "继续学习与研究任务", keywords: "workflow" },
  { key: "tasks", title: "处理进度", path: "/workflow?view=processing", detail: "后台任务与失败重试", keywords: "tasks progress" },
  { key: "actions", title: "自动行动清单", path: "/actions", detail: "查看已保存清单", keywords: "actions" },
  { key: "roadmap", title: "学习路线", path: "/roadmap", detail: "查看学习安排", keywords: "roadmap" },
  { key: "learn", title: "逐步学习", path: "/learn", detail: "基础讲解、小测与代码练习", keywords: "learn tutor python 学习" },
  {key:"notebook",title:"我的笔记",path:"/settings?tab=notebook",detail:"跨设备保存的笔记和草稿"},
  { key: "settings", title: "个人设置", path: "/settings", detail: "账号、学习方式与辅导模型", keywords: "api model profile settings 注册 登录 模型" },
];

export default function QuickLauncher() {
  const {preferences}=usePreferences();
  const [open, setOpen] = useState(false), [query, setQuery] = useState("");
  const [knowledge,setKnowledge]=useState<Entry[]>([]);
  const [extras,setExtras]=useState<Entry[]>([]);const [extraError,setExtraError]=useState("");
  const [papers, setPapers] = useState<QuickPaper[]>([]), [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState(""), [retry, setRetry] = useState(0), [active, setActive] = useState(0);
  const input = useRef<InputRef>(null), returnFocus = useRef<HTMLElement | null>(null), generation = useRef(0);
  const trigger = useRef<HTMLElement | null>(null);
  const location = useLocation(), navigate = useNavigate(), id = useId();
  const listId = `atlas-launcher-${id}`, term = query.trim();

  function show() {
    const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    returnFocus.current = focused?.closest('[role="dialog"]') ? trigger.current : focused;
    window.dispatchEvent(new Event("atlas:close-context-search"));
    window.dispatchEvent(new Event("atlas:close-navigation"));
    setQuery(""); setActive(0); setOpen(true);
  }

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.isComposing || event.repeat || event.shiftKey || event.altKey || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k") return;
      event.preventDefault();
      if (open) setOpen(false); else show();
    };
    const close = () => { returnFocus.current = null; setOpen(false); };
    const focus = () => { if (open) input.current?.focus(); };
    window.addEventListener("keydown", keyboard);
    window.addEventListener("atlas:close-quick-launcher", close);
    window.addEventListener("atlas:focus-quick-launcher", focus);
    return () => { window.removeEventListener("keydown", keyboard); window.removeEventListener("atlas:close-quick-launcher", close); window.removeEventListener("atlas:focus-quick-launcher", focus); };
  }, [open]);

  useEffect(() => { setOpen(false); }, [location.key]);

  useEffect(() => {
    const request = ++generation.current;
    setPapers([]); setExtras([]); setKnowledge([]); setError("");setExtraError(""); setStatus(open && term ? "loading" : "idle");
    if (!open || !term) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void apiGet<{items:{kind:string;title:string;snippet:string;url:string}[]}>("/api/workbench/search",{q:term},controller.signal).then(r=>{if(!controller.signal.aborted&&generation.current===request)setExtras(r.items.filter(x=>x.kind!=="论文").map((x,i)=>({key:`global:${i}`,title:x.title,path:x.url,detail:x.kind+" · "+x.snippet.slice(0,80)})))}).catch(e=>{if(!controller.signal.aborted&&generation.current===request)setExtraError("课题与笔记搜索暂不可用，论文查找仍可使用。")});
      if(preferences.features.graph)void getUnifiedGraph({q:term,limit:8},controller.signal).then(result=>{if(!controller.signal.aborted&&generation.current===request)setKnowledge((result.nodes||[]).map(n=>({key:'knowledge:'+n.id,title:n.label,path:n.scope?.kind==='project'?'/research/'+n.scope.project_id+'?view=graph&node='+n.id:'/graph?node='+n.id,detail:'知识 · '+(n.scope?.title||'资料库')+' · '+(n.source_title||n.kind)})))}).catch(()=>{});
      void quickFindPapers(term, controller.signal).then(result => {
        if (!controller.signal.aborted && generation.current === request) {
          setPapers(result.items); setStatus("done");
        }
      }).catch(caught => {
        if (!controller.signal.aborted && generation.current === request) {
          setError(caught instanceof Error ? caught.message : String(caught)); setStatus("error");
        }
      });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [open, term, retry]);

  const entries = useMemo(() => {
    const needle = term.toLocaleLowerCase();
    const commands = destinations.filter(item => (item.key!=="graph"||preferences.features.graph)&&(item.key!=="roadmap"||preferences.features.roadmap)&&(item.key!=="learn"||["foundations","quizzes","coding","paper_guidance"].some(key=>preferences.features[key as keyof typeof preferences.features]))&&`${item.title} ${item.detail} ${item.keywords}`.toLocaleLowerCase().includes(needle));
    const matches: Entry[] = papers.map(paper => ({ key: `paper:${paper.uid}`, title: paper.title || paper.uid,
      path: `/papers/${encodeURIComponent(paper.uid)}?tab=reading`, detail: `论文${paper.year ? ` · ${paper.year}` : ""}` }));
    return [...commands, ...knowledge, ...matches, ...extras, ...(term ? [{ key: "query", title: `在论文库查找“${term}”`,
      path: `/manage?${new URLSearchParams({ q: term })}`, detail: "打开完整列表与筛选" }] : [])];
  }, [papers, extras, knowledge, term,preferences.features]);

  const selected = entries[Math.min(active, Math.max(0, entries.length - 1))];
  const selectedId = selected ? `${listId}-${selected.key}` : undefined;
  function choose(entry: Entry) { setOpen(false); navigate(entry.path); }

  useEffect(() => {
    if (open && selectedId) document.getElementById(selectedId)?.scrollIntoView?.({ block: "nearest" });
  }, [selectedId, open]);

  return <>
    <Button ref={element => { trigger.current = element; }} className="atlas-launcher-trigger" icon={<SearchOutlined />} onClick={show}
      aria-label="快速查找与跳转" aria-keyshortcuts="Control+k Meta+k">
      <span>快速查找</span><kbd>Ctrl / ⌘ K</kbd>
    </Button>
    <Modal title="快速查找与跳转" open={open} onCancel={() => setOpen(false)} footer={null} width={640}
      focusTriggerAfterClose={false} afterOpenChange={visible => { if (visible) input.current?.focus(); }}
      afterClose={() => { if (returnFocus.current?.isConnected) returnFocus.current.focus(); }}>
      {extraError&&<p role="status">{extraError}</p>}
      <Input ref={input} value={query} maxLength={120} allowClear placeholder="搜索知识、方法、公式、论文或课题"
        aria-label="查找论文或页面" role="combobox" aria-expanded={open} aria-controls={listId}
        aria-autocomplete="list" aria-activedescendant={selectedId}
        onChange={event => { setQuery(event.target.value); setActive(0); }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing || event.keyCode === 229) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setActive(current => (current + (event.key === "ArrowDown" ? 1 : -1) + entries.length) % entries.length);
          } else if (event.key === "Enter" && selected) { event.preventDefault(); choose(selected); }
          else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); }
        }} />
      <div className="atlas-launcher-notice" aria-live="polite" aria-busy={status === "loading"}>
        {!term && "输入关键词搜索知识与资料，或选择快捷入口。"}
        {term && status === "loading" && "正在查找个人资料库…"}
        {term && status === "done" && (papers.length+extras.length+knowledge.length ? `找到 ${knowledge.length} 个知识节点、${papers.length} 篇论文和 ${extras.length} 条其他记录` : "没有匹配记录，可调整关键词。")}
      </div>
      {!!error && <Alert type="warning" showIcon message="论文查找暂不可用" description={error}
        action={<Button size="small" onClick={() => setRetry(value => value + 1)}>重试查找</Button>} />}
      <div id={listId} role="listbox" aria-label="论文与快捷入口" className="atlas-launcher-list">
        {entries.map((entry, index) => <div key={entry.key} id={`${listId}-${entry.key}`} role="option"
          aria-selected={entry === selected} className="atlas-launcher-option" onMouseEnter={() => setActive(index)}
          onMouseDown={event => event.preventDefault()} onClick={() => choose(entry)}>
          <span><strong>{entry.title}</strong><small>{entry.detail}</small></span><span aria-hidden="true">↗</span>
        </div>)}
      </div>
      <p className="atlas-launcher-help">↑ ↓ 选择 · Enter 打开 · Esc 关闭</p>
    </Modal>
  </>;
}

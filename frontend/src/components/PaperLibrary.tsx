import { useEffect, useRef, useState } from "react";
import { Alert, Button, Checkbox, Empty, Input, Pagination, Radio, Select, Space, Spin, Table, Tag, message } from "antd";
import { BookFilled, BookOutlined, ReloadOutlined, StarFilled, StarOutlined } from "@ant-design/icons";
import { Link, useSearchParams } from "react-router-dom";
import { listLibraryPapers, updateLibraryPaper, type LibraryFilter, type LibraryPage, type LibraryPaper } from "../api/library";
import { apiPost } from "../api/client";
import { startExtract } from "../api/papers";
import { useAccessMode } from "./SessionContext";
import "./paper-library.css";

const PAGE_SIZE = 20;
const filterLabels = { all: "全部论文", starred: "收藏", read_later: "稍后阅读" };
const statusLabels: Record<string, string> = { parsed: "已解析", pending: "待解析", queued: "排队中", running: "解析中", failed: "解析失败" };
const sourceLabels: Record<string, string> = { upload: "上传 PDF", arxiv: "arXiv", manual: "手动添加", local: "本地资料", demo: "示例资料", semantic_scholar: "Semantic Scholar", openalex: "OpenAlex" };
const MOBILE_QUERY = "(max-width: 767px)";

function useMobileList() {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY);
    const changed = (event: MediaQueryListEvent) => setMobile(event.matches);
    setMobile(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  return mobile;
}

function PaperStatus({ paper }: { paper: LibraryPaper }) {
  const status = Object.prototype.hasOwnProperty.call(statusLabels, paper.parse_status) ? paper.parse_status : "unknown";
  return <Tag className={`atlas-library-status atlas-library-status--${status}`}>
    {statusLabels[status] || "状态未记录"}
  </Tag>;
}

function PaperSource({ paper }: { paper: LibraryPaper }) {
  return <Tag className="atlas-library-source">{sourceLabels[paper.source] || "其他来源"}</Tag>;
}

function PaperMetadata({ paper }: { paper: LibraryPaper }) {
  const authors = Array.isArray(paper.authors) ? paper.authors : [];
  return <span className="atlas-library-paper-meta">{paper.year && paper.year > 0 ? paper.year : "年份未记录"}
    {!!authors.length && <> · {authors.slice(0, 2).join("、")}{authors.length > 2 ? " 等" : ""}</>}
  </span>;
}

export default function PaperLibrary({ refreshVersion = 0, projectId, projectPaperUids, onProjectChange }: { refreshVersion?: number; projectId?:string; projectPaperUids?:string[]; onProjectChange?:()=>void }) {
  const multiuser = useAccessMode() === "multiuser";
  const mobile = useMobileList();
  const [params, setParams] = useSearchParams();
  const requestedFilter = params.get("filter");
  const filter: LibraryFilter = requestedFilter === "starred" || requestedFilter === "read_later" ? requestedFilter : "all";
  const page = Math.max(1, Math.floor(Number(params.get("page")) || 1));
  const q = params.get("q") || "", parseStatus = params.get("status") || "";
  const [draft, setDraft] = useState(q);
  const [data, setData] = useState<LibraryPage>({ total: 0, items: [] });
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [selected, setSelected] = useState<React.Key[]>([]), [extracting, setExtracting] = useState(false);
  const [refresh, setRefresh] = useState(0), [saving, setSaving] = useState<Set<string>>(new Set());
  const pending = useRef(new Set<string>()), mounted = useRef(true);
  const [linking,setLinking]=useState<Set<string>>(new Set()),[linkedHere,setLinkedHere]=useState<Set<string>>(new Set()),[linkError,setLinkError]=useState("");
  const linkPending=useRef(new Set<string>());const projectScope=useRef(projectId);projectScope.current=projectId;
  useEffect(()=>{setLinkedHere(new Set());setLinkError("")},[projectId]);
  const linked=new Set([...(projectPaperUids||[]),...linkedHere]);
  async function addToProject(uids:string[]) {
    if(!projectId||!projectPaperUids)return;
    const scope=projectId;setLinkError("");let changed=false;
    for(const uid of uids){if(linked.has(uid)||linkPending.current.has(uid))continue;linkPending.current.add(uid);setLinking(new Set(linkPending.current));
      try{const r=await apiPost<{linked:boolean}>(`/api/workbench/projects/${encodeURIComponent(scope)}/papers`,{paper_uid:uid});if(!r.linked)throw new Error("未收到关联确认");changed=true;if(mounted.current&&projectScope.current===scope)setLinkedHere(old=>new Set([...old,uid]));}
      catch(e){if(mounted.current&&projectScope.current===scope)setLinkError(`未能加入研究空间：${String(e)}`);break;}
      finally{linkPending.current.delete(uid);if(mounted.current&&projectScope.current===scope)setLinking(new Set(linkPending.current));}
    }
    if(changed&&mounted.current&&projectScope.current===scope)onProjectChange?.();
  }
  const projectAction=(paper:LibraryPaper)=>projectId&&<Button size="small" aria-label={`${linked.has(paper.uid)?"已加入研究空间":"加入研究空间"}：${paper.title}`} disabled={!projectPaperUids||linked.has(paper.uid)} loading={linking.has(paper.uid)} onClick={()=>void addToProject([paper.uid])}>{linked.has(paper.uid)?"已加入研究空间":"加入研究空间"}</Button>;

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setDraft(q); }, [q]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setData({ total: 0, items: [] }); setSelected([]);
    listLibraryPapers({ filter, q, parse_status: parseStatus || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }, controller.signal)
      .then(result => {
        if (controller.signal.aborted) return;
        const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
        if (page > lastPage) {
          setParams(old => { const next = new URLSearchParams(old); next.set("page", String(lastPage)); return next; }, { replace: true });
          return;
        }
        setData(result);
      })
      .catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filter, q, parseStatus, page, refresh, refreshVersion, setParams]);

  function changeCriteria(changes: Record<string, string | undefined>) {
    setParams(old => {
      const next = new URLSearchParams(old);
      for (const [key, value] of Object.entries(changes)) value ? next.set(key, value) : next.delete(key);
      next.set("page", "1");
      return next;
    });
  }

  async function toggle(paper: LibraryPaper, field: "starred" | "read_later") {
    if (pending.current.has(paper.uid)) return;
    pending.current.add(paper.uid); setSaving(new Set(pending.current)); setError("");
    try {
      await updateLibraryPaper(paper.uid, { [field]: !paper[field] });
      if (mounted.current) setRefresh(value => value + 1);
    } catch (caught) {
      if (mounted.current) setError(`未能保存“${paper.title}”的资料架标记：${String(caught)}`);
    } finally {
      pending.current.delete(paper.uid);
      if (mounted.current) setSaving(new Set(pending.current));
    }
  }

  async function extractSelected() {
    if (multiuser) return;
    setExtracting(true); setError("");
    try {
      for (const uid of selected) await startExtract(String(uid));
      if (mounted.current) message.success("抽取任务已提交");
    } catch (caught) { if (mounted.current) setError(String(caught)); }
    finally { if (mounted.current) setExtracting(false); }
  }

  const hasFilters = filter !== "all" || !!q || !!parseStatus;
  const emptyText = error ? "列表暂不可用，请重试。" : loading ? "正在加载论文…" : q || parseStatus ? "没有符合筛选条件的论文。" : filter === "all" ? "上传 PDF 后，论文会显示在这里。" : `暂无${filterLabels[filter]}论文，可从全部论文中添加。`;
  const readingPath = (paper: LibraryPaper) => projectId&&linked.has(paper.uid)?`/research/${encodeURIComponent(projectId)}?tab=reading&paper=${encodeURIComponent(paper.uid)}`:`/papers/${encodeURIComponent(paper.uid)}?tab=reading${projectId?`&project=${encodeURIComponent(projectId)}`:""}`;
  const readLink = (paper: LibraryPaper) => <Link className="atlas-library-read" to={readingPath(paper)} aria-label={`阅读原文：${paper.title}`}>阅读原文</Link>;
  const markers = (paper: LibraryPaper) => <Space size={6} className="atlas-library-markers">
    <Button size="small" className={paper.starred ? "atlas-library-marker is-active" : "atlas-library-marker"}
      icon={paper.starred ? <StarFilled aria-hidden /> : <StarOutlined aria-hidden />}
      aria-label={`${paper.starred ? "取消收藏" : "收藏"}：${paper.title}`} aria-pressed={!!paper.starred}
      disabled={loading || saving.has(paper.uid)} onClick={() => void toggle(paper, "starred")}>{paper.starred ? "已收藏" : "收藏"}</Button>
    <Button size="small" className={paper.read_later ? "atlas-library-marker is-active" : "atlas-library-marker"}
      icon={paper.read_later ? <BookFilled aria-hidden /> : <BookOutlined aria-hidden />}
      aria-label={`${paper.read_later ? "移出稍后阅读" : "加入稍后阅读"}：${paper.title}`} aria-pressed={!!paper.read_later}
      disabled={loading || saving.has(paper.uid)} onClick={() => void toggle(paper, "read_later")}>{paper.read_later ? "已加入" : "稍后读"}</Button>
  </Space>;
  const setPage = (value: number) => setParams(old => { const next = new URLSearchParams(old); next.set("page", String(value)); return next; });

  return <section className="atlas-library" aria-labelledby="atlas-library-title">
    <header className="atlas-library-heading">
      <h2 id="atlas-library-title">我的论文</h2>
      <span className="atlas-library-count" aria-live="polite">{loading ? "正在加载…" : <>{data.total} 篇{hasFilters ? "匹配" : "论文"}</>}</span>
    </header>
    <div className="atlas-library-toolbar">
      <Radio.Group aria-label="资料架视图" optionType="button" buttonStyle="solid" value={filter}
        options={Object.entries(filterLabels).map(([value, label]) => ({ value, label }))}
        onChange={event => changeCriteria({ filter: event.target.value })} />
      <div className="atlas-library-search-row">
        <Input.Search aria-label="论文库关键词" placeholder="搜索标题或摘要" value={draft} allowClear className="atlas-library-search"
          onChange={event => setDraft(event.target.value)} onSearch={value => changeCriteria({ q: value.trim() })} />
        <Select aria-label="论文解析状态" placeholder="全部解析状态" allowClear className="atlas-library-status-filter" value={parseStatus || undefined}
          options={[{ value: "parsed", label: "已解析" }, { value: "pending", label: "待解析" }]}
          onChange={value => changeCriteria({ status: value })} />
        <Button icon={<ReloadOutlined aria-hidden />} onClick={() => setRefresh(value => value + 1)}>刷新列表</Button>
      </div>
    </div>
    {(hasFilters || !!draft) && <div className="atlas-library-context">
      <span aria-live="polite">{q ? `关键词“${q}”` : filter !== "all" ? filterLabels[filter] : parseStatus ? statusLabels[parseStatus] || "其他解析状态" : ""}</span>
      <Button type="text" size="small" onClick={() => { setDraft(""); changeCriteria({ filter: undefined, q: undefined, status: undefined }); }}>清空筛选</Button>
    </div>}
    {linkError&&<Alert className="atlas-library-error" type="error" message={linkError} description="已成功加入的论文会保留；可重新点击未加入论文的按钮。"/>}
    {error && <Alert className="atlas-library-error" type="error" showIcon message="论文列表或标记操作失败" description={error}
        action={<Button onClick={() => setRefresh(value => value + 1)}>重试列表</Button>} />}
    <div className="atlas-library-selection">
      <span>{selected.length ? `已选择 ${selected.length} 篇论文` : multiuser ? "" : "勾选论文后可批量抽取"}</span>
      <Space wrap>{projectId&&<Button size="small" disabled={!projectPaperUids||!selected.some(uid=>!linked.has(String(uid)))||loading} loading={linking.size>0} onClick={()=>void addToProject(selected.map(String))}>将所选加入研究空间</Button>}<Button size="small" disabled={multiuser || !selected.length || loading || extracting} loading={extracting} onClick={() => void extractSelected()}>批量抽取</Button></Space>
    </div>
    {multiuser && <p className="atlas-library-mode-note">多人试用暂未开放模型抽取；可阅读原文、收藏并安排稍后阅读。</p>}
    <div className="atlas-library-results" aria-busy={loading}>
      {mobile ? <>
        {loading ? <div className="atlas-library-loading" role="status"><Spin size="small" />正在加载论文…</div> : data.items.length ? <>
          <Checkbox className="atlas-library-select-page" aria-label="选择本页全部论文"
            checked={data.items.every(paper => selected.includes(paper.uid))} indeterminate={!!selected.length && !data.items.every(paper => selected.includes(paper.uid))}
            onChange={event => setSelected(event.target.checked ? data.items.map(paper => paper.uid) : [])}>选择本页</Checkbox>
          <div className="atlas-library-cards">{data.items.map(paper => <article className="atlas-library-paper" key={paper.uid} aria-label={`论文：${paper.title}`}>
            <div className="atlas-library-paper-top"><Checkbox aria-label={`选择论文：${paper.title}`} checked={selected.includes(paper.uid)}
              onChange={event => setSelected(old => event.target.checked ? [...old, paper.uid] : old.filter(key => key !== paper.uid))} />
              <Space size={4} wrap><PaperSource paper={paper} /><PaperStatus paper={paper} /></Space>
            </div>
            <h3><Link to={readingPath(paper)}>{paper.title}</Link></h3><PaperMetadata paper={paper} />
            <div className="atlas-library-paper-actions">{readLink(paper)}{projectAction(paper)}{markers(paper)}</div>
          </article>)}</div>
        </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />}
      </> : <Table<LibraryPaper> rowKey="uid" loading={loading} dataSource={data.items} scroll={{ x: 720 }} size="middle"
        locale={{ emptyText }}
        rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
        pagination={false}
        columns={[
          { title: "论文", dataIndex: "title", render: (title, paper) => <div className="atlas-library-title-cell"><Link to={readingPath(paper)}>{title}</Link><PaperMetadata paper={paper} /></div> },
          { title: "来源", width: 104, render: (_, paper) => <PaperSource paper={paper} /> },
          { title: "解析状态", width: 108, render: (_, paper) => <PaperStatus paper={paper} /> },
          { title: "阅读与标记", width: 204, render: (_, paper) => <div className="atlas-library-row-actions">{readLink(paper)}{projectAction(paper)}{markers(paper)}</div> },
        ]} />}
    </div>
    <footer className="atlas-library-footer"><span>{loading ? "正在加载…" : data.total ? `本页 ${data.items.length} 篇` : ""}</span>
      <Pagination current={page} pageSize={PAGE_SIZE} total={data.total} showSizeChanger={false} hideOnSinglePage
        size={mobile ? "small" : undefined} onChange={setPage} />
    </footer>
  </section>;
}

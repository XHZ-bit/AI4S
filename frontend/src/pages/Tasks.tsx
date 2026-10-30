import { useEffect, useState } from "react";
import { Alert, Button, Progress, Select, Space, Table, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";

const taskNames: Record<string,string> = {collect:"资料采集",parse:"PDF 解析",download:"获取与提取全文",ingest:"资料入库",extract:"知识提取",guide:"阅读解读",roadmap:"学习路线"};
function phaseName(value?: string) {
  if (!value) return "等待阶段记录";
  const batch = /^(extract|guide):(\d+)\/(\d+)$/.exec(value);
  if (batch) return `${batch[1] === "extract" ? "知识提取" : "阅读解读"}：第 ${batch[2]}/${batch[3]} 段`;
  return ({queued:"等待执行",prepare:"准备资料",download:"下载原文",parse:"解析版面",extract:"提取知识",index:"建立检索索引",complete:"处理完成",research:"研究分析"} as Record<string,string>)[value] || value;
}

export default function Tasks() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true, active = false, failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    async function poll() {
      if (!live || active || document.hidden) return;
      active = true; controller = new AbortController();
      try {
        const result = await apiGet<any>("/api/system/tasks", { status, offset: (page-1)*20, limit:20 }, controller.signal);
        if (live) { setItems(result.items); setTotal(result.total); setError(""); failures = 0; }
      } catch (caught) { if (live && !controller.signal.aborted) { setError(String(caught)); failures++; } }
      finally {
        active = false;
        if (live && !document.hidden) timer = setTimeout(() => void poll(), Math.min(30000, 3000 * 2 ** failures));
      }
    }
    function visibility() { if (timer) clearTimeout(timer); if (document.hidden) controller?.abort(); else void poll(); }
    void poll(); document.addEventListener("visibilitychange", visibility);
    return () => { live = false; if (timer) clearTimeout(timer); controller?.abort(); document.removeEventListener("visibilitychange", visibility); };
  }, [page, status, refresh]);
  async function operate(item: any, action: "cancel" | "retry") {
    const key = `${item.kind}:${item.id}`; setBusy(key);
    try {
      const path = action === "cancel" ? `/api/system/tasks/${item.kind}/${item.id}/cancel` : item.kind === "research" ? `/api/projects/tasks/${item.id}/retry` : `/api/learning/tasks/${item.id}/retry`;
      await apiPost(path); setError(""); setRefresh(value => value+1);
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(undefined); }
  }
  return <><Typography.Title level={2}>处理进度</Typography.Title>
    <Typography.Paragraph>汇总资料处理与课题任务。取消会在安全边界停止后续操作；已保存阶段保留。模型和外部下载的中断任务需主动重试。</Typography.Paragraph>
    <Space style={{marginBottom:16}}><Select allowClear aria-label="任务状态筛选" placeholder="全部状态" style={{width:170}} value={status} onChange={value => {setStatus(value);setPage(1);}} options={Object.entries({queued:"排队中",running:"处理中",done:"已完成",failed:"失败",cancelled:"已取消",interrupted:"已中断"}).map(([value,label]) => ({value,label}))}/><Button onClick={() => setRefresh(value => value+1)}>刷新任务</Button></Space>
    {error && <Alert type="error" message="任务加载或操作失败" description={error}/>}
    <Table<any> rowKey={item => `${item.kind}:${item.id}`} dataSource={items} scroll={{x:1000}} pagination={{current:page,pageSize:20,total,showSizeChanger:false,onChange:setPage}} columns={[
      {title:"任务",render:(_,item)=><Link to={item.url}>{item.label === "collect" ? "采集论文资料" : item.label}</Link>}, {title:"类型",dataIndex:"type",render:value=>taskNames[value]||value},
      {title:"状态",dataIndex:"status",render:value=><Tag color={value==="done"?"green":value==="failed"?"red":"blue"}>{({queued:"排队中",running:"处理中",done:"已完成",failed:"失败",cancelled:"已取消",interrupted:"已中断"} as Record<string,string>)[value]||value}</Tag>},
      {title:"阶段",render:(_,item)=><div>{phaseName(item.phase)}{item.progress!=null&&<Progress percent={Math.round(item.progress*100)} size="small"/>}{item.elapsed_seconds!=null&&<small>{item.status==="running"?"已运行":"用时"} {item.elapsed_seconds} 秒</small>}{item.overdue&&<Tag color="orange">已超过时限，等待安全边界</Tag>}</div>},
      {title:"原因",render:(_,item)=><div>{item.error_code && <Tag>{item.error_code}</Tag>}{item.error}{item.error&&<p>{/401|403|key|token|密钥/i.test(item.error)?"检查个人模型设置及服务权限，再重试当前任务。":/timeout|timed out|超时|connect|network/i.test(item.error)?"连接或响应超时；已保存的原文保留，恢复网络后可重试当前阶段。":/pdf|parse|解析/i.test(item.error)?"检查原始 PDF 是否可打开；可重新提交解析，无需删除已有论文。":"查看错误详情并修正输入后重试；已有记录继续保留。"}</p>}{item.warnings?.map((warning:any,index:number)=><p key={index}>{typeof warning==="string"?warning:`${warning.stage || ""}: ${warning.error || ""}`}</p>)}</div>},
      {title:"操作",render:(_,item)=><Space>{item.can_cancel&&<Button loading={busy===`${item.kind}:${item.id}`} onClick={()=>void operate(item,"cancel")}>取消任务</Button>}{item.can_retry&&<Button loading={busy===`${item.kind}:${item.id}`} onClick={()=>void operate(item,"retry")}>重试任务</Button>}</Space>}
    ]}/>
  </>;
}

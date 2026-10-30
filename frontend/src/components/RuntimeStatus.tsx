import { useEffect, useState } from "react";
import { Alert, Button, Tag } from "antd";
import { DownOutlined, ReloadOutlined, SettingOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import { useAccessMode, type AccessMode } from "./SessionContext";
import "./runtime-status.css";

interface ServiceStatus { status: string; reason?: string; knowledge_enabled?: boolean; knowledge_backend?: string }
interface RuntimeData {
  mode: string;
  access_mode?: AccessMode;
  data_dir: string;
  services: { database: ServiceStatus; graph: ServiceStatus; parser: ServiceStatus; model: ServiceStatus };
  capabilities: { graph: boolean; research_model: boolean; knowledge_model?: boolean };
}

export default function RuntimeStatus() {
  const accessMode = useAccessMode();
  const [data, setData] = useState<RuntimeData>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setData(undefined); setError("");
    apiGet<RuntimeData>("/api/system/status", undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refresh]);
  const privateWorkspace = accessMode === "multiuser" || data?.access_mode === "multiuser";
  const workspaceAvailable = data?.services.database.status === "available";
  const knowledgeEnabled = privateWorkspace ? false : data?.capabilities.knowledge_model ?? data?.services.model.knowledge_enabled;
  const knowledgeParser = data?.services.parser.knowledge_backend;
  return <section className={`atlas-runtime-status${data && !workspaceAvailable ? " has-storage-error" : ""}`} aria-label="运行状态">
    <div className="atlas-runtime-overview"><div className="atlas-runtime-heading"><i className={error || data && !workspaceAvailable ? "is-error" : loading ? "is-loading" : "is-ready"} aria-hidden="true" /><h3>运行状态</h3>
      {data && <span className="atlas-runtime-mode">{privateWorkspace ? "受控多人 · 个人空间" : "本机单用户"}</span>}
      {data && <span className={`atlas-runtime-storage${workspaceAvailable ? "" : " is-error"}`}>本地数据库：{workspaceAvailable ? "可用" : "不可用"}</span>}
      {data && <Tag>知识模型：{knowledgeEnabled === true ? "已启用" : knowledgeEnabled === false ? "未启用" : "状态未提供"}</Tag>}
    </div><Button size="small" type="text" icon={<ReloadOutlined aria-hidden="true" />} loading={loading} onClick={() => setRefresh(value => value + 1)}>检查状态</Button></div>
    {error && <Alert className="atlas-runtime-alert" type="error" showIcon message="运行状态读取失败" description={<>{error}<p>请确认网络和工作台服务可用，再点击“检查状态”；持续失败时联系维护者。</p></>} />}
    {data && <>
      {!workspaceAvailable && <Alert className="atlas-runtime-alert" type="error" showIcon message="资料存储暂不可用" description={<>{privateWorkspace ? "请联系维护者检查个人资料存储；修复后点击“检查状态”。" : "请检查数据目录权限与磁盘空间；修复后点击“检查状态”。"}{data.services.database.reason && <p>{data.services.database.reason}</p>}</>} />}
      {workspaceAvailable && <div className="atlas-runtime-next"><span>可以继续阅读与整理资料</span><nav aria-label="可继续的资料操作"><Link to="/manage">导入或查找论文</Link><Link to="/tasks">查看处理进度</Link><Link to="/actions">整理行动清单</Link></nav></div>}
      {workspaceAvailable && knowledgeEnabled === true && <p>知识模型已启用：上传到研究空间后，会按预算自动解析与分析；深入讲解和方法比较由你主动发起。</p>}
      <details className="atlas-runtime-details"><summary><SettingOutlined aria-hidden="true" /><span>服务详情</span><DownOutlined className="atlas-runtime-chevron" aria-hidden="true" /></summary><div className="atlas-runtime-details-body">
        <div className="atlas-runtime-services"><Tag>{data.mode === "docker" ? "Docker 模式" : "本地模式"}</Tag><Tag>图服务：{data.capabilities.graph ? "可用" : "不可用"}</Tag><Tag>{knowledgeParser ? "新资料解析：" + knowledgeParser : "解析：" + (data.services.parser.status === "available" ? "GROBID" : "本地文字解析")}</Tag><Tag>原研究计划模型：{data.capabilities.research_model ? "已配置并开启" : "未开启"}</Tag></div>
        <p className="atlas-runtime-directory">当前数据目录：{privateWorkspace ? "个人空间（仅当前账号可见）" : data.data_dir}</p>
        {privateWorkspace && <div className="atlas-runtime-capability-note"><strong>个人资料与操作记录按账号隔离</strong><p>可上传 PDF、阅读原文、文字检索和整理行动清单。远程采集、模型抽取与共享图服务暂未开放；{knowledgeParser ? "新资料使用上述已配置的解析后端。" : "文字解析不会执行 OCR。"}</p></div>}
        {!privateWorkspace && knowledgeEnabled === false && <p>知识模型未启用时，仍可上传、阅读和整理资料。自动知识分析需要维护者配置并开启平台模型。</p>}
        {!privateWorkspace && knowledgeEnabled === undefined && <p>当前服务尚未返回知识模型状态，请更新服务或检查平台配置。原研究计划模型的开关单独控制旧研究流程。</p>}
        {Object.entries(data.services).map(([key, value]) => value.reason && (key !== "database" || workspaceAvailable) && <p key={key}>{key === "parser" && knowledgeParser ? "旧文档解析：" : ""}{value.reason}</p>)}
      </div></details>
    </>}
    {!data && !error && <p className="atlas-runtime-loading" role="status">正在检查本地服务…</p>}
  </section>;
}

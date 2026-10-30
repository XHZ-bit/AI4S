import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, test, vi } from "vitest";
import { apiGet } from "../api/client";
import RuntimeStatus from "../components/RuntimeStatus";
import { AccessModeProvider } from "../components/SessionContext";

vi.mock("../api/client", () => ({ apiGet: vi.fn() }));
afterEach(() => vi.resetAllMocks());

const status = {
  mode: "local", data_dir: "isolated/data",
  services: { database: { status: "available" }, graph: { status: "unavailable", reason: "图服务未启动" }, parser: { status: "fallback" }, model: { status: "unconfigured" } },
  capabilities: { graph: false, research_model: false },
};

test("the verified multiuser mode explains capabilities and hides server paths even with older status fields", async () => {
  vi.mocked(apiGet).mockResolvedValue({ ...status, data_dir: "C:/private-server/users/alice" });
  render(<MemoryRouter><AccessModeProvider mode="multiuser"><RuntimeStatus /></AccessModeProvider></MemoryRouter>);
  expect(await screen.findByText("受控多人 · 个人空间")).toBeTruthy();
  const details = screen.getByText("服务详情").closest("details")!;
  expect(details.open).toBe(false);
  fireEvent.click(screen.getByText("服务详情"));
  expect(details.open).toBe(true);
  expect(screen.getByText(/远程采集、模型抽取与共享图服务暂未开放/)).toBeTruthy();
  expect(screen.queryByText(/C:\/private-server/)).toBeNull();
  expect(screen.getByRole("link", { name: "导入或查找论文" }).getAttribute("href")).toBe("/manage");
  expect(screen.getByRole("link", { name: "查看处理进度" }).getAttribute("href")).toBe("/tasks");
  expect(apiGet).toHaveBeenCalledTimes(1);
  expect(apiGet).toHaveBeenCalledWith("/api/system/status", undefined, expect.any(AbortSignal));
});

test("local mode keeps useful offline next steps when optional services are unavailable", async () => {
  vi.mocked(apiGet).mockResolvedValue(status);
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  expect(await screen.findByText("本机单用户")).toBeTruthy();
  expect(screen.getByText(/当前服务尚未返回知识模型状态/)).toBeTruthy();
  expect(screen.getByText("图服务未启动")).toBeTruthy();
  expect(screen.getByRole("link", { name: "整理行动清单" }).getAttribute("href")).toBe("/actions");
});

test("a failed refresh removes stale healthy status and offers a concrete retry action", async () => {
  vi.mocked(apiGet).mockResolvedValueOnce(status).mockRejectedValueOnce(new Error("503 connection refused"));
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  await screen.findByText("本机单用户");
  await waitFor(() => expect(screen.getByRole("button", { name: "检查状态" }).className).not.toContain("loading"));
  fireEvent.click(screen.getByRole("button", { name: "检查状态" }));
  expect(await screen.findByText("运行状态读取失败")).toBeTruthy();
  expect(screen.queryByText("本地数据库：可用")).toBeNull();
  expect(screen.getByText(/请确认网络和工作台服务可用/)).toBeTruthy();
});

test("an unavailable personal store directs users to maintenance without advertising working actions", async () => {
  vi.mocked(apiGet).mockResolvedValue({ ...status, access_mode: "multiuser", data_dir: "/srv/private/alice", services: { ...status.services, database: { status: "unavailable", reason: "存储权限不足" } } });
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  expect(await screen.findByText("资料存储暂不可用")).toBeTruthy();
  expect(screen.getByText("资料存储暂不可用").closest("details")).toBeNull();
  expect(screen.getByText("存储权限不足").closest("details")).toBeNull();
  expect(screen.getByText(/请联系维护者检查个人资料存储/)).toBeTruthy();
  expect(screen.queryByRole("link", { name: "导入或查找论文" })).toBeNull();
  expect(screen.queryByText(/\/srv\/private/)).toBeNull();
});

test("technical details stay collapsed initially while useful next steps remain visible", async () => {
  vi.mocked(apiGet).mockResolvedValue(status);
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  await screen.findByText("本机单用户");
  const details = screen.getByText("服务详情").closest("details")!;
  expect(details.open).toBe(false);
  expect(screen.getByText("图服务未启动").closest("details")).toBe(details);
  expect(screen.getByRole("link", { name: "导入或查找论文" }).closest("details")).toBeNull();
  fireEvent.click(screen.getByText("服务详情"));
  expect(details.open).toBe(true);
  fireEvent.click(screen.getByText("服务详情"));
  expect(details.open).toBe(false);
});

test("enabled knowledge model explains automatic upload analysis even when the original research model is off", async () => {
  vi.mocked(apiGet).mockResolvedValue({ ...status, capabilities: { ...status.capabilities, knowledge_model: true }, services: { ...status.services, model: { status: "available", knowledge_enabled: true }, parser: { status: "fallback", knowledge_backend: "Docling" } } });
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  expect(await screen.findByText("知识模型：已启用")).toBeTruthy();
  const explanation = screen.getByText(/上传到研究空间后，会按预算自动解析与分析/);
  expect(explanation.closest("details")).toBeNull();
  expect(screen.getByText("新资料解析：Docling")).toBeTruthy();
  expect(screen.getByText("原研究计划模型：未开启")).toBeTruthy();
  expect(screen.queryByText(/不会自动调用模型/)).toBeNull();
});

test("knowledge parser and model service fields are respected without relabeling an available parser as GROBID", async () => {
  vi.mocked(apiGet).mockResolvedValue({ ...status, services: { ...status.services, model: { status: "disabled", knowledge_enabled: false }, parser: { status: "available", knowledge_backend: "PyMuPDF", reason: "旧扫描件不执行 OCR" } } });
  render(<MemoryRouter><RuntimeStatus /></MemoryRouter>);
  expect(await screen.findByText("知识模型：未启用")).toBeTruthy();
  expect(screen.getByText("新资料解析：PyMuPDF")).toBeTruthy();
  expect(screen.queryByText("解析：GROBID")).toBeNull();
  expect(screen.getByText("旧文档解析：旧扫描件不执行 OCR")).toBeTruthy();
  expect(screen.getByText(/自动知识分析需要维护者配置并开启平台模型/)).toBeTruthy();
});

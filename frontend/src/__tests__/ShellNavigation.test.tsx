import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { vi } from "vitest";
import Shell from "../components/Shell";
vi.mock("../components/workbench/useRecentProjects", () => ({default:()=>({items:[{id:"p1",title:"人机协作"}],loading:false,error:""})}));
vi.mock("../components/workspace/Workspace", () => ({ default: ({ children }: any) => children }));
vi.mock("../components/WorkflowSummary", () => ({ default: () => null }));
vi.mock("../components/QuickLauncher", () => ({ default: () => <button>快速查找</button> }));
function Location() { return <output data-testid="route">{useLocation().pathname}</output>; }
function mount(url: string, mobile = false) {
  const query = { matches: mobile, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.spyOn(window, "matchMedia").mockReturnValue(query as any);
  return render(<MemoryRouter initialEntries={[url]}><Shell><h1>page content</h1><Location /></Shell></MemoryRouter>);
}
afterEach(() => vi.restoreAllMocks());

test("sidebar can collapse and reopen while retaining navigation and the saved preference", () => {
  localStorage.setItem("atlas:sidebar-collapsed", "false");
  mount("/manage");
  fireEvent.click(screen.getByRole("button", {name: "收起功能栏"}));
  expect(localStorage.getItem("atlas:sidebar-collapsed")).toBe("true");
  expect(screen.getByRole("link", {name: "全部课题"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "展开功能栏"}));
  expect(screen.getByRole("button", {name: "收起功能栏"}).getAttribute("aria-expanded")).toBe("true");
});

test("desktop navigation names the active section and keeps a keyboard skip target", () => {
  mount("/manage");
  const nav = screen.getByRole("navigation", { name: "主导航" });
  expect(within(nav).getByRole("link", { name: "资料库" }).getAttribute("aria-current")).toBe("page");
  expect(within(nav).getByRole("link", { name: "工作台" }).hasAttribute("aria-current")).toBe(false);
  expect(within(nav).getByRole('link',{name:'知识图谱'}).getAttribute('href')).toBe('/graph');
  expect(within(nav).getAllByRole('link')).toHaveLength(4);
  expect(within(screen.getByRole('navigation',{name:'最近研究空间'})).getByRole('link',{name:'人机协作'}).getAttribute('href')).toBe('/research/p1');
  expect(screen.getByRole('link',{name:'设置'}).getAttribute('href')).toBe('/settings');
  expect(screen.getByRole('link',{name:'任务面板'}).getAttribute('href')).toBe('/workflow');
  expect(screen.getByRole('link',{name:'登录 / 注册'}).getAttribute('href')).toBe('/settings?tab=account');
  expect(document.title).toBe('资料库 · PaperStride');
  expect(screen.getByText("跳到主要内容").getAttribute("href")).toBe("#atlas-main-content");
  expect(document.getElementById("atlas-main-content")?.getAttribute("tabindex")).toBe("-1");
});

test("mobile more menu exposes secondary destinations, closes after navigation, and marks the current route", async () => {
  mount("/manage", true);
  const nav = screen.getByRole("navigation", { name: "主导航" });
  expect(within(nav).queryByRole("link", { name: "学习路线" })).toBeNull();
  fireEvent.click(within(nav).getByRole("button", { name: "更多页面" }));
  const menu = await screen.findByRole("navigation", { name: "更多页面" });
  fireEvent.click(within(menu).getByRole("link", { name: "全部课题" }));
  await waitFor(() => expect(screen.getByTestId("route").textContent).toBe("/research"));
  await waitFor(() => expect(screen.queryByRole("navigation", { name: "更多页面" })).toBeNull());
  expect(within(nav).getByRole("button", { name: "更多页面" }).getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(within(nav).getByRole("button", { name: "更多页面" }));
  expect(await screen.findByRole("link", { name: "全部课题" })).toBeTruthy();
});

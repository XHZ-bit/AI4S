import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigationType } from "react-router-dom";
import { ConfigProvider, Skeleton, theme as antdTheme } from "antd";
import "./components/workbench/paperstride.css";
import "./components/experience.css";
import zhCN from "antd/locale/zh_CN";
import Shell from "./components/Shell";
import SessionGate from "./components/SessionGate";
import {usePreferences} from "./components/PreferencesContext";
import PreferencesProvider from "./components/PreferencesContext";
import {Link} from "react-router-dom";
import type {ReactNode} from "react";
import { applyTheme, getInitialTheme, THEME_STORAGE_KEY, ThemeContext } from "./theme";

const Explore = lazy(() => import("./pages/Explore"));
const DiffusionPractice = lazy(() => import("./components/workbench/DiffusionPractice"));
const CaseStudy = lazy(() => import("./pages/CaseStudy"));
const Home = lazy(() => import("./pages/Home"));
const Graph = lazy(() => import("./pages/Graph"));
const Paper = lazy(() => import("./pages/PaperDetail"));
const Quality = lazy(() => import("./pages/Quality"));
const Manage = lazy(() => import("./pages/Manage"));
const Roadmap = lazy(() => import("./pages/Roadmap"));
const PersonalizedRoadmapDemo = lazy(() => import("./pages/PersonalizedRoadmapDemo"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Actions = lazy(() => import("./pages/Actions"));
const WorkflowHub = lazy(() => import("./pages/WorkflowHub"));
const ResearchProjectsPage = lazy(() => import("./pages/research/ResearchProjectsPage"));
const ResearchProjectPage = lazy(() => import("./pages/research/ResearchProjectPage"));
const ProjectGraph = lazy(() => import("./pages/research/ProjectGraph"));
const Settings = lazy(() => import("./pages/Settings"));
const Learn = lazy(() => import("./pages/Learn"));
const ResearchPrintPage = lazy(() => import("./pages/research/ResearchPrintPage"));

function AppRoutes() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();
  const previousPath = useRef(pathname);
  useLayoutEffect(()=>{if(previousPath.current!==pathname&&navigationType!=="POP")window.scrollTo(0,0);previousPath.current=pathname},[pathname,navigationType]);
  const {loading:preferencesLoading}=usePreferences();
  if(preferencesLoading)return <Skeleton active paragraph={{rows:6}}/>;
  const routes = <Suspense fallback={<div aria-label="工作空间加载中"><Skeleton active paragraph={{rows:8}} /></div>}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/cases/:caseId" element={<CaseStudy />} />
      <Route path="/explore" element={<Explore/>}/>
      <Route path="/practice" element={<DiffusionPractice/>}/>
      <Route path="/graph" element={<FeatureGate feature="graph"><Graph /></FeatureGate>} />
      <Route path="/settings" element={<Settings/>}/>
      <Route path="/learn" element={<Learn/>}/>
      <Route path="/papers/:uid" element={<Paper />} />
      <Route path="/manage" element={<Manage />} />
      <Route path="/roadmap" element={<FeatureGate feature="roadmap"><Roadmap /></FeatureGate>} />
      <Route path="/demo/personalized-roadmap" element={<FeatureGate feature="roadmap"><PersonalizedRoadmapDemo /></FeatureGate>} />
      <Route path="/tasks" element={<Tasks />} />
      <Route path="/actions" element={<Actions />} />
      <Route path="/workflow" element={<WorkflowHub />} />
      <Route path="/research" element={<ResearchProjectsPage />} />
      <Route path="/research/:projectId" element={<ResearchProjectPage />} />
      <Route path="/research/:projectId/graph" element={<ProjectGraph />} />
      <Route path="/research/:projectId/print/:snapshotId" element={<ResearchPrintPage />} />
      <Route path="/admin/quality" element={<Quality />} />
      <Route path="/review" element={<Navigate to="/admin/quality" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </Suspense>;
  return pathname.includes("/print/") ? routes : <Shell>{routes}</Shell>;
}

export default function App() {
  const [mode, setMode] = useState(getInitialTheme);
  useEffect(() => { applyTheme(mode); }, [mode]);
  useEffect(() => {
    const syncTheme = (event: StorageEvent) => {
      if (event.key === THEME_STORAGE_KEY && (event.newValue === "light" || event.newValue === "dark")) setMode(event.newValue);
    };
    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);
  const context = useMemo(() => ({ mode, toggle: () => setMode(current => current === "light" ? "dark" : "light") }), [mode]);
  const dark = mode === "dark";
  return <ThemeContext.Provider value={context}>
    <ConfigProvider locale={zhCN} theme={{
      algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: dark ? "#a3c9ad" : "#365e4e",
        colorInfo: dark ? "#a3c9ad" : "#365e4e",
        colorLink: dark ? "#b5d8bc" : "#365e4e",
        colorText: dark ? "#e9ece5" : "#252e2b",
        colorTextSecondary: dark ? "#adb7aa" : "#646c64",
        colorTextTertiary: dark ? "#a1ac9e" : "#666f64",
        colorTextQuaternary: dark ? "#9aa695" : "#767e73",
        colorTextPlaceholder: dark ? "#a1ac9e" : "#666f64",
        colorTextDisabled: dark ? "#899583" : "#7c8478",
        colorBorder: dark ? "#3b453c" : "#dddfd5",
        colorBorderSecondary: dark ? "#3b453c" : "#e6e7df",
        colorBgBase: dark ? "#212824" : "#ffffff",
        colorBgContainer: dark ? "#252d28" : "#ffffff",
        colorBgElevated: dark ? "#252d28" : "#ffffff",
        colorBgLayout: dark ? "#1b211e" : "#faf9f6",
        borderRadius: 7,
        fontSize: 15,
        fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        controlHeight: 40,
      },
      components: {
        Card: { borderRadiusLG: 10 },
        Button: { primaryShadow: "none", primaryColor: dark ? "#1b211e" : "#ffffff" },
        Tabs: { horizontalItemGutter: 24 },
        Table: { headerBg: dark ? "#252d28" : "#faf9f6", cellPaddingBlock: 15 },
      },
    }}>
      <SessionGate><PreferencesProvider><BrowserRouter><AppRoutes /></BrowserRouter></PreferencesProvider></SessionGate>
    </ConfigProvider>
  </ThemeContext.Provider>;
}

function FeatureGate({feature,children}:{feature:"graph"|"roadmap";children:ReactNode}){
 const {preferences,loading}=usePreferences();
 if(loading)return <Skeleton active/>;
 return preferences.features[feature]?children:<section><h1>此功能已关闭</h1><Link to="/settings">前往个人设置重新开启</Link></section>;
}

import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ConfigProvider, Skeleton } from "antd";
import Shell from "./components/Shell";

const CaseStudy = lazy(() => import("./pages/CaseStudy"));
const Home = lazy(() => import("./pages/Home"));
const Graph = lazy(() => import("./pages/Graph"));
const Paper = lazy(() => import("./pages/PaperDetail"));
const Quality = lazy(() => import("./pages/Quality"));
const Manage = lazy(() => import("./pages/Manage"));
const Roadmap = lazy(() => import("./pages/Roadmap"));
const PersonalizedRoadmapDemo = lazy(() => import("./pages/PersonalizedRoadmapDemo"));
const Tasks = lazy(() => import("./pages/Tasks"));
const WorkflowHub = lazy(() => import("./pages/WorkflowHub"));
const ResearchProjectsPage = lazy(() => import("./pages/research/ResearchProjectsPage"));
const ResearchProjectPage = lazy(() => import("./pages/research/ResearchProjectPage"));
const ProjectGraph = lazy(() => import("./pages/research/ProjectGraph"));
const ResearchPrintPage = lazy(() => import("./pages/research/ResearchPrintPage"));

function AppRoutes() {
  const { pathname } = useLocation();
  const routes = <Suspense fallback={<div aria-label="工作空间加载中"><Skeleton active paragraph={{rows:8}} /></div>}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/cases/:caseId" element={<CaseStudy />} />
      <Route path="/graph" element={<Graph />} />
      <Route path="/papers/:uid" element={<Paper />} />
      <Route path="/manage" element={<Manage />} />
      <Route path="/roadmap" element={<Roadmap />} />
      <Route path="/demo/personalized-roadmap" element={<PersonalizedRoadmapDemo />} />
      <Route path="/tasks" element={<Tasks />} />
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
  return <ConfigProvider theme={{ token: { colorPrimary: "#147d92", borderRadius: 10 } }}>
    <BrowserRouter><AppRoutes /></BrowserRouter>
  </ConfigProvider>;
}

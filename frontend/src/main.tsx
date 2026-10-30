import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "antd/dist/reset.css";
import { applyTheme, getInitialTheme } from "./theme";

applyTheme(getInitialTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);

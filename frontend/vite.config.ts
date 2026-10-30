import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react(), {name:"python-runtime-cors",configureServer(server){server.middlewares.use((request,response,next)=>{
    if(/^\/python-(?:runtime\/|worker\.js)/.test(request.url||""))response.setHeader("Access-Control-Allow-Origin","*");
    next();
  });},configurePreviewServer(server){server.middlewares.use((request,response,next)=>{
    if(/^\/python-(?:runtime\/|worker\.js)/.test(request.url||""))response.setHeader("Access-Control-Allow-Origin","*");
    next();
  });}}],
  server: { proxy: { "/api": {
    target: process.env.ATLAS_API_TARGET || "http://127.0.0.1:8000",
    // Keep the browser's original authority for the API's Origin/Host check.
    changeOrigin: false,
  } } },
});

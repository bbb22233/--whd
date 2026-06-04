import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" → 构建产物可从任意路径/同源反代提供(对齐部署 spec 档2/3)。
// dev 代理:把 /api 转给 FastAPI(8000),前端走同源、无需 CORS。
// (/reports、/data 静态回退在 dev 一般不触发——主路 /api 经代理已通;生产由 server.mjs/反代提供。)
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});

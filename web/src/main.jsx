import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// 真正加载 webfont(离线打包):Inter 做拉丁/UI,JetBrains Mono 做对齐数字。
// 中文由系统字体(苹方/雅黑)承接 —— 字体栈在 styles.css 里定义。
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

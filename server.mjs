import { createServer } from "node:http";
import { existsSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT ?? 4177);
const host = process.env.HOST ?? "127.0.0.1";   // 档2/3 内网/反代时设 HOST=0.0.0.0

// 前端根:优先 React 构建产物 web/dist(`cd web && npm run build`),否则回退旧 legacy 根。
const webDist = path.join(root, "web", "dist");
const appRoot = existsSync(path.join(webDist, "index.html")) ? webDist : root;
// 数据回退(/reports、/data)始终从仓库根目录提供,不在 web/dist 里。
const DATA_PREFIXES = ["reports/", "data/"];

const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".csv", "text/csv; charset=utf-8"],
  [".txt", "text/plain; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".ico", "image/x-icon"],
  [".woff2", "font/woff2"],
]);

function resolveRequestPath(requestUrl) {
  const url = new URL(requestUrl, "http://localhost");
  const requestPath = decodeURIComponent(url.pathname);
  const relativePath = requestPath === "/" ? "index.html" : requestPath.replace(/^\/+/, "");
  // 拒绝 dotfile / 隐藏段(.git、.env 等)
  if (relativePath.split("/").some((segment) => segment.startsWith("."))) return null;
  // /reports、/data 从仓库根;其余从前端根(web/dist 或 legacy)
  const base = DATA_PREFIXES.some((p) => relativePath.startsWith(p)) ? root : appRoot;
  const filePath = path.resolve(base, relativePath);
  const relative = path.relative(base, filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  // 扩展名白名单:其余(源码/配置/无扩展名)一律 403
  if (!mimeTypes.has(path.extname(filePath).toLowerCase())) return null;
  return filePath;
}

const server = createServer(async (request, response) => {
  try {
    const filePath = resolveRequestPath(request.url ?? "/");
    if (!filePath) {
      response.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
      response.end("Forbidden");
      return;
    }

    const info = await stat(filePath);
    if (!info.isFile()) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end("Not found");
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const body = await readFile(filePath);
    response.writeHead(200, {
      "content-type": mimeTypes.get(ext) ?? "application/octet-stream",
      "cache-control": "no-store",
    });
    response.end(body);
  } catch (error) {
    const status = error?.code === "ENOENT" ? 404 : 500;
    response.writeHead(status, { "content-type": "text/plain; charset=utf-8" });
    response.end(status === 404 ? "Not found" : "Server error");
  }
});

server.listen(port, host, () => {
  console.log(`Market weather terminal: http://${host}:${port}`);
});

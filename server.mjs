import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT ?? 4177);

const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".csv", "text/csv; charset=utf-8"],
  [".txt", "text/plain; charset=utf-8"],
]);

function resolveRequestPath(requestUrl) {
  const url = new URL(requestUrl, "http://localhost");
  const requestPath = decodeURIComponent(url.pathname);
  const relativePath = requestPath === "/" ? "index.html" : requestPath.replace(/^\/+/, "");
  // M3: reject dotfiles / hidden segments (e.g. .git, .env) up front.
  if (relativePath.split("/").some((segment) => segment.startsWith("."))) return null;
  const filePath = path.resolve(root, relativePath);
  const relative = path.relative(root, filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  // M3: allowlist by known extension; everything else (source, configs, no-ext) is 403.
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

server.listen(port, "127.0.0.1", () => {
  console.log(`Market weather terminal: http://127.0.0.1:${port}`);
});

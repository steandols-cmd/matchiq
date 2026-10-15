// Reservbygge utan Vite (används i miljöer utan paketregister). Samma källkod, samma utdata-struktur.
import { build } from "esbuild";
import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "dist");
mkdirSync(resolve(out, "assets"), { recursive: true });
await build({
  entryPoints: [resolve(root, "src/main.tsx")],
  bundle: true,
  minify: true,
  format: "esm",
  target: "es2022",
  jsx: "automatic",
  outfile: resolve(out, "assets/app.js"),
  loader: { ".svg": "text" },
  define: { "process.env.NODE_ENV": '"production"' },
  nodePaths: (process.env.NODE_PATH || "").split(":").filter(Boolean),
  logLevel: "info",
});
let html = readFileSync(resolve(root, "index.html"), "utf8");
html = html.replace(/<script type="module" src="\/src\/main.tsx"><\/script>/,
  '<link rel="stylesheet" href="./assets/app.css"><script type="module" src="./assets/app.js"></script>');
writeFileSync(resolve(out, "index.html"), html);
cpSync(resolve(root, "public"), out, { recursive: true });

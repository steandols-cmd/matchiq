import { defineConfig } from "vite";

// React-JSX hanteras av esbuild (inbyggt i Vite) – inga extra plugins behövs.
export default defineConfig({
  base: "./",
  esbuild: { jsx: "automatic" },
  build: { outDir: "dist", sourcemap: false, target: "es2022", chunkSizeWarningLimit: 1500 },
  server: { port: 5173, strictPort: true },
});

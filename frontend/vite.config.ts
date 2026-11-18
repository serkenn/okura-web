// 画面のビルド（Vite + React）。出力は frontend/dist（Python のサーバーがそのまま配る）
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const root = fileURLToPath(new URL('.', import.meta.url));
// 開発のときだけ：API を手元のサーバーへ中継する（既定は架空のデータの試験用サーバー）
const api = process.env.OKURA_API || 'http://127.0.0.1:8799';

export default defineConfig({
  root,
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false, target: 'es2022' },
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': { target: api, changeOrigin: true } } },
});

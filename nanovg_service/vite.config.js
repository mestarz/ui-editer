import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'web',
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/api': 'http://localhost:3002'
    }
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true
  },
  plugins: [react()]
});

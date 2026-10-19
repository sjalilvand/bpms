import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// در توسعه: پورت ۳۰۰۰ با پروکسی API به بک‌اند ۸۰۰۰
// در عملیات: خروجی build توسط FastAPI سرو می‌شود
export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {}, // جلوگیری از خواندن postcss.config ریشه پروژه
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1600,
  },
});

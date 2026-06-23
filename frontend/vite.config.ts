import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/contacts': 'http://127.0.0.1:8000',
      '/deals': 'http://127.0.0.1:8000',
      '/accounts': 'http://127.0.0.1:8000',
      '/pipeline': 'http://127.0.0.1:8000',
      '/activities': 'http://127.0.0.1:8000',
      '/reminders': 'http://127.0.0.1:8000',
      '/forecast': 'http://127.0.0.1:8000',
      '/saved-views': 'http://127.0.0.1:8000',
      '/stats': 'http://127.0.0.1:8000',
      '/tags': 'http://127.0.0.1:8000',
      '/outbox': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
});

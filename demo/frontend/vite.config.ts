import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 800 },   // recharts chiếm phần lớn bundle; app chạy local nên chấp nhận
  server: {
    proxy: {
      '/api': { target: backend, ws: true },
      '/evidence': backend,
      '/labeling': backend,
    },
  },
})

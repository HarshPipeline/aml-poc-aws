import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  base: '/kyc-assets/',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8001',
      '/backend': { target: 'http://127.0.0.1:8001', rewrite: path => path.replace(/^\/backend/, '') },
    },
  },
})

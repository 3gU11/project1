import { defineConfig } from 'vite'
import legacy from '@vitejs/plugin-legacy'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

const API_TARGET = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
const PHOTO_API_TARGET = process.env.VITE_PHOTO_API_TARGET || 'http://localhost:3001'
const photoApiProxy = {
  target: PHOTO_API_TARGET,
  changeOrigin: true,
}

export default defineConfig({
  plugins: [
    vue(),
    legacy({
      targets: ['defaults', 'Safari >= 12', 'iOS >= 12'],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api/v1/photo-items': photoApiProxy,
      '/api/v1/ocr-field-rules': photoApiProxy,
      '/api/v1/model-dictionary': photoApiProxy,
      '/api/v1/machines': photoApiProxy,
      '/api/v1/photo-tasks': photoApiProxy,
      '/api/v1/photo-files': photoApiProxy,
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})

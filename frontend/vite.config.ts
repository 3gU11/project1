import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const API_TARGET = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
const PHOTO_API_TARGET = process.env.VITE_PHOTO_API_TARGET || 'http://localhost:3001'
const photoApiProxy = {
  target: PHOTO_API_TARGET,
  changeOrigin: true,
}

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia'],
      resolvers: [ElementPlusResolver()],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: 'src/components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
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
    // Ensure all routes fallback to index.html for SPA routing
    historyApiFallback: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const mId = id.replace(/\\/g, '/')
          if (mId.includes('/node_modules/vue/') || mId.includes('/node_modules/@vue/')) return 'vendor-vue'
          if (mId.includes('/node_modules/vue-router/')) return 'vendor-vue'
          if (mId.includes('/node_modules/pinia/')) return 'vendor-vue'
          if (mId.includes('/node_modules/axios/')) return 'vendor-utils'
          if (mId.includes('/node_modules/mammoth/')) return 'vendor-utils'
          return undefined
        },
      },
    },
  },
})

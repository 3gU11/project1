// vite.config.ts
import { defineConfig } from "file:///E:/V8/project1/frontend/node_modules/vite/dist/node/index.js";
import vue from "file:///E:/V8/project1/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import path from "path";
import AutoImport from "file:///E:/V8/project1/frontend/node_modules/unplugin-auto-import/dist/vite.mjs";
import Components from "file:///E:/V8/project1/frontend/node_modules/unplugin-vue-components/dist/vite.mjs";
import { ElementPlusResolver } from "file:///E:/V8/project1/frontend/node_modules/unplugin-vue-components/dist/resolvers.mjs";
var __vite_injected_original_dirname = "E:\\V8\\project1\\frontend";
var vite_config_default = defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ["vue", "vue-router", "pinia"],
      resolvers: [ElementPlusResolver()],
      dts: "src/auto-imports.d.ts"
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: "css" })],
      dts: "src/components.d.ts"
    })
  ],
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "./src")
    }
  },
  server: {
    port: 3e3,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
        ws: true
      }
    },
    // Ensure all routes fallback to index.html for SPA routing
    historyApiFallback: true
  },
  test: {
    environment: "jsdom",
    globals: true
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const mId = id.replace(/\\/g, "/");
          if (mId.includes("/node_modules/vue/") || mId.includes("/node_modules/@vue/")) return "vendor-vue";
          if (mId.includes("/node_modules/vue-router/")) return "vendor-vue";
          if (mId.includes("/node_modules/pinia/")) return "vendor-vue";
          if (mId.includes("/node_modules/axios/")) return "vendor-utils";
          if (mId.includes("/node_modules/mammoth/")) return "vendor-utils";
          return void 0;
        }
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJFOlxcXFxWOFxcXFxwcm9qZWN0MVxcXFxmcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiRTpcXFxcVjhcXFxccHJvamVjdDFcXFxcZnJvbnRlbmRcXFxcdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL0U6L1Y4L3Byb2plY3QxL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcclxuaW1wb3J0IHZ1ZSBmcm9tICdAdml0ZWpzL3BsdWdpbi12dWUnXHJcbmltcG9ydCBwYXRoIGZyb20gJ3BhdGgnXHJcbmltcG9ydCBBdXRvSW1wb3J0IGZyb20gJ3VucGx1Z2luLWF1dG8taW1wb3J0L3ZpdGUnXHJcbmltcG9ydCBDb21wb25lbnRzIGZyb20gJ3VucGx1Z2luLXZ1ZS1jb21wb25lbnRzL3ZpdGUnXHJcbmltcG9ydCB7IEVsZW1lbnRQbHVzUmVzb2x2ZXIgfSBmcm9tICd1bnBsdWdpbi12dWUtY29tcG9uZW50cy9yZXNvbHZlcnMnXHJcblxyXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xyXG4gIHBsdWdpbnM6IFtcclxuICAgIHZ1ZSgpLFxyXG4gICAgQXV0b0ltcG9ydCh7XHJcbiAgICAgIGltcG9ydHM6IFsndnVlJywgJ3Z1ZS1yb3V0ZXInLCAncGluaWEnXSxcclxuICAgICAgcmVzb2x2ZXJzOiBbRWxlbWVudFBsdXNSZXNvbHZlcigpXSxcclxuICAgICAgZHRzOiAnc3JjL2F1dG8taW1wb3J0cy5kLnRzJyxcclxuICAgIH0pLFxyXG4gICAgQ29tcG9uZW50cyh7XHJcbiAgICAgIHJlc29sdmVyczogW0VsZW1lbnRQbHVzUmVzb2x2ZXIoeyBpbXBvcnRTdHlsZTogJ2NzcycgfSldLFxyXG4gICAgICBkdHM6ICdzcmMvY29tcG9uZW50cy5kLnRzJyxcclxuICAgIH0pLFxyXG4gIF0sXHJcbiAgcmVzb2x2ZToge1xyXG4gICAgYWxpYXM6IHtcclxuICAgICAgJ0AnOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCAnLi9zcmMnKSxcclxuICAgIH0sXHJcbiAgfSxcclxuICBzZXJ2ZXI6IHtcclxuICAgIHBvcnQ6IDMwMDAsXHJcbiAgICBwcm94eToge1xyXG4gICAgICAnL2FwaSc6IHtcclxuICAgICAgICB0YXJnZXQ6IHByb2Nlc3MuZW52LlZJVEVfUFJPWFlfVEFSR0VUIHx8ICdodHRwOi8vbG9jYWxob3N0OjgwMDAnLFxyXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcclxuICAgICAgICB3czogdHJ1ZSxcclxuICAgICAgfSxcclxuICAgIH0sXHJcbiAgICAvLyBFbnN1cmUgYWxsIHJvdXRlcyBmYWxsYmFjayB0byBpbmRleC5odG1sIGZvciBTUEEgcm91dGluZ1xyXG4gICAgaGlzdG9yeUFwaUZhbGxiYWNrOiB0cnVlLFxyXG4gIH0sXHJcbiAgdGVzdDoge1xyXG4gICAgZW52aXJvbm1lbnQ6ICdqc2RvbScsXHJcbiAgICBnbG9iYWxzOiB0cnVlLFxyXG4gIH0sXHJcbiAgYnVpbGQ6IHtcclxuICAgIGNodW5rU2l6ZVdhcm5pbmdMaW1pdDogODAwLFxyXG4gICAgcm9sbHVwT3B0aW9uczoge1xyXG4gICAgICBvdXRwdXQ6IHtcclxuICAgICAgICBtYW51YWxDaHVua3MoaWQpIHtcclxuICAgICAgICAgIGNvbnN0IG1JZCA9IGlkLnJlcGxhY2UoL1xcXFwvZywgJy8nKVxyXG4gICAgICAgICAgaWYgKG1JZC5pbmNsdWRlcygnL25vZGVfbW9kdWxlcy92dWUvJykgfHwgbUlkLmluY2x1ZGVzKCcvbm9kZV9tb2R1bGVzL0B2dWUvJykpIHJldHVybiAndmVuZG9yLXZ1ZSdcclxuICAgICAgICAgIGlmIChtSWQuaW5jbHVkZXMoJy9ub2RlX21vZHVsZXMvdnVlLXJvdXRlci8nKSkgcmV0dXJuICd2ZW5kb3ItdnVlJ1xyXG4gICAgICAgICAgaWYgKG1JZC5pbmNsdWRlcygnL25vZGVfbW9kdWxlcy9waW5pYS8nKSkgcmV0dXJuICd2ZW5kb3ItdnVlJ1xyXG4gICAgICAgICAgaWYgKG1JZC5pbmNsdWRlcygnL25vZGVfbW9kdWxlcy9heGlvcy8nKSkgcmV0dXJuICd2ZW5kb3ItdXRpbHMnXHJcbiAgICAgICAgICBpZiAobUlkLmluY2x1ZGVzKCcvbm9kZV9tb2R1bGVzL21hbW1vdGgvJykpIHJldHVybiAndmVuZG9yLXV0aWxzJ1xyXG4gICAgICAgICAgcmV0dXJuIHVuZGVmaW5lZFxyXG4gICAgICAgIH0sXHJcbiAgICAgIH0sXHJcbiAgICB9LFxyXG4gIH0sXHJcbn0pXHJcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBK1AsU0FBUyxvQkFBb0I7QUFDNVIsT0FBTyxTQUFTO0FBQ2hCLE9BQU8sVUFBVTtBQUNqQixPQUFPLGdCQUFnQjtBQUN2QixPQUFPLGdCQUFnQjtBQUN2QixTQUFTLDJCQUEyQjtBQUxwQyxJQUFNLG1DQUFtQztBQU96QyxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTO0FBQUEsSUFDUCxJQUFJO0FBQUEsSUFDSixXQUFXO0FBQUEsTUFDVCxTQUFTLENBQUMsT0FBTyxjQUFjLE9BQU87QUFBQSxNQUN0QyxXQUFXLENBQUMsb0JBQW9CLENBQUM7QUFBQSxNQUNqQyxLQUFLO0FBQUEsSUFDUCxDQUFDO0FBQUEsSUFDRCxXQUFXO0FBQUEsTUFDVCxXQUFXLENBQUMsb0JBQW9CLEVBQUUsYUFBYSxNQUFNLENBQUMsQ0FBQztBQUFBLE1BQ3ZELEtBQUs7QUFBQSxJQUNQLENBQUM7QUFBQSxFQUNIO0FBQUEsRUFDQSxTQUFTO0FBQUEsSUFDUCxPQUFPO0FBQUEsTUFDTCxLQUFLLEtBQUssUUFBUSxrQ0FBVyxPQUFPO0FBQUEsSUFDdEM7QUFBQSxFQUNGO0FBQUEsRUFDQSxRQUFRO0FBQUEsSUFDTixNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUEsTUFDTCxRQUFRO0FBQUEsUUFDTixRQUFRLFFBQVEsSUFBSSxxQkFBcUI7QUFBQSxRQUN6QyxjQUFjO0FBQUEsUUFDZCxJQUFJO0FBQUEsTUFDTjtBQUFBLElBQ0Y7QUFBQTtBQUFBLElBRUEsb0JBQW9CO0FBQUEsRUFDdEI7QUFBQSxFQUNBLE1BQU07QUFBQSxJQUNKLGFBQWE7QUFBQSxJQUNiLFNBQVM7QUFBQSxFQUNYO0FBQUEsRUFDQSxPQUFPO0FBQUEsSUFDTCx1QkFBdUI7QUFBQSxJQUN2QixlQUFlO0FBQUEsTUFDYixRQUFRO0FBQUEsUUFDTixhQUFhLElBQUk7QUFDZixnQkFBTSxNQUFNLEdBQUcsUUFBUSxPQUFPLEdBQUc7QUFDakMsY0FBSSxJQUFJLFNBQVMsb0JBQW9CLEtBQUssSUFBSSxTQUFTLHFCQUFxQixFQUFHLFFBQU87QUFDdEYsY0FBSSxJQUFJLFNBQVMsMkJBQTJCLEVBQUcsUUFBTztBQUN0RCxjQUFJLElBQUksU0FBUyxzQkFBc0IsRUFBRyxRQUFPO0FBQ2pELGNBQUksSUFBSSxTQUFTLHNCQUFzQixFQUFHLFFBQU87QUFDakQsY0FBSSxJQUFJLFNBQVMsd0JBQXdCLEVBQUcsUUFBTztBQUNuRCxpQkFBTztBQUFBLFFBQ1Q7QUFBQSxNQUNGO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=

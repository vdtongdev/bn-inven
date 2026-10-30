import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: {
    watch: { usePolling: true, interval: 500 },
  },
  plugins: [react(), VitePWA({
    registerType: 'autoUpdate',
    includeAssets: ['icon.svg'],
    manifest: {
      name: 'BN-Inven — Danh mục hàng hóa', short_name: 'BN-Inven', lang: 'vi',
      description: 'Số hóa danh mục sản phẩm từ ảnh nhãn hàng hóa', theme_color: '#0f766e', background_color: '#f8fafc', display: 'standalone', start_url: '/',
      icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' }],
    },
    workbox: { navigateFallback: '/index.html', globPatterns: ['**/*.{js,css,html,svg,ico,png}'] },
  })],
})

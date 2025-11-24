import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/ERP-Final/',
  plugins: [react()],
  server: {
    port: 5173,
  },
})

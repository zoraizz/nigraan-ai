import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The Aid Priority live pipeline fetches its sample tiles from
// /sample-images — bundled static assets served from public/sample-images/
// (copied from damage-checker/sample-images/) by both the dev server and
// the production build (vite build copies public/ into dist/).

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
})

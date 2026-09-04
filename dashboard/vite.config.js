import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const projectRoot = path.dirname(fileURLToPath(import.meta.url))

// Dev-server route: GET /sample-images/<file> serves the real tiles from
// damage-checker/sample-images/ (the repo-committed demo imagery documented
// in that folder's README). The Aid Priority live pipeline fetches these and
// POSTs them to Damage Checker's /classify-damage. Dev-server only; the demo
// dashboard runs on the dev server (see dashboard/INTEGRATION.md).
function serveSampleImages() {
  const sampleImagesDir = path.resolve(projectRoot, '../damage-checker/sample-images')
  return {
    name: 'serve-damage-checker-sample-images',
    configureServer(server) {
      server.middlewares.use('/sample-images', (req, res, next) => {
        const name = path.basename(decodeURIComponent(req.url || ''))
        const file = path.join(sampleImagesDir, name)
        if (req.method !== 'GET' || !name.endsWith('.png') || !fs.existsSync(file)) {
          next()
          return
        }
        res.setHeader('Content-Type', 'image/png')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), serveSampleImages()],
})

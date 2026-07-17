import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(dirname, '..')
const python = process.platform === 'win32'
  ? path.join(repoRoot, '.venv', 'Scripts', 'python.exe')
  : path.join(repoRoot, '.venv', 'bin', 'python')
const dbPath = path.join(repoRoot, 'e2e.sqlite3').replaceAll('\\', '/')

export default defineConfig({
  testDir: './e2e',
  timeout: 45000,
  expect: { timeout: 8000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173/ERP-Final/',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" ../manage.py migrate --noinput && "${python}" ../manage.py seed_billing_e2e && "${python}" ../manage.py runserver 127.0.0.1:8000`,
      url: 'http://127.0.0.1:8000/admin/login/',
      reuseExistingServer: false,
      timeout: 60000,
      env: {
        DJANGO_DEBUG: 'true',
        DJANGO_SECRET_KEY: 'e2e-secret-key-at-least-32-bytes-long',
        DATABASE_URL: `sqlite:///${dbPath}`,
        ARCA_PROVIDER: 'mock',
        ARCA_DEFAULT_POINT_OF_SALE: '5',
        ARCA_DEFAULT_VOUCHER_TYPE: '11',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 60000,
      env: {
        VITE_API_BASE_URL: 'http://127.0.0.1:8000/api',
      },
    },
  ],
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})

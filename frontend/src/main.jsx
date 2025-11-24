import React from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App.jsx'

const basePath = ((import.meta.env.BASE_URL || '/').replace(/\/$/, '') || '/')
const currentPath = window.location.pathname

if (!window.location.hash && currentPath.startsWith(basePath) && currentPath.length > basePath.length) {
  let extra = currentPath.slice(basePath.length)
  if (extra && extra !== '/') {
    if (!extra.startsWith('/')) {
      extra = `/${extra}`
    }
    const normalizedBase = basePath === '/' ? '' : basePath
    window.location.replace(`${normalizedBase}/#${extra}`)
  }
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </HashRouter>
  </React.StrictMode>
)

import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './auth/AuthProvider.jsx'
import './styles/index.css'

// HashRouter (not BrowserRouter): the dashboard is deployed as a static site
// on Render, whose free static hosting serves /index.html only for the root
// path -- a BrowserRouter sub-path like /aid-priority would 404 on refresh or
// deep link without a server-side rewrite rule (the Render API does not
// expose one). Hash-based routes (/#/aid-priority) need no rewrites.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </HashRouter>
  </React.StrictMode>,
)

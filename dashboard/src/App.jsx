import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar.jsx'
import Header from './components/layout/Header.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Overview from './pages/Overview.jsx'
import RiskMap from './pages/RiskMap.jsx'
import DamageAssessment from './pages/DamageAssessment.jsx'
import AidPriority from './pages/AidPriority.jsx'
import FloodTracker from './pages/FloodTracker.jsx'
import { SceneDamageProvider } from './scene/SceneDamageProvider.jsx'

// Console shell: persistent sidebar rail + header around the 4 console pages.
function ConsoleShell() {
  // Start collapsed on phone widths so the page, not the menu, fills the screen.
  const [isCollapsed, setIsCollapsed] = useState(() => window.innerWidth < 768)

  const toggleSidebar = () => setIsCollapsed((prev) => !prev)

  return (
    <div className="flex min-h-screen bg-[#030b06] text-slate-100">
      <Sidebar isCollapsed={isCollapsed} toggleSidebar={toggleSidebar} />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col transition-all duration-300">
        <Header isCollapsed={isCollapsed} toggleSidebar={toggleSidebar} />
        <main className="flex-1 overflow-x-hidden p-4 lg:p-6">
          <Routes>
            <Route
              path="/overview"
              element={
                <ProtectedRoute>
                  <Overview />
                </ProtectedRoute>
              }
            />
            <Route
              path="/risk-map"
              element={
                <ProtectedRoute>
                  <RiskMap />
                </ProtectedRoute>
              }
            />
            <Route
              path="/damage-assessment"
              element={
                <ProtectedRoute>
                  <DamageAssessment />
                </ProtectedRoute>
              }
            />
            <Route
              path="/aid-priority"
              element={
                <ProtectedRoute>
                  <AidPriority />
                </ProtectedRoute>
              }
            />
            {/* flood: River Flood Tracker */}
            <Route
              path="/flood-tracker"
              element={
                <ProtectedRoute>
                  <FloodTracker />
                </ProtectedRoute>
              }
            />
            {/* ground: old Ground Reports page now lives in Damage Assessment */}
            <Route
              path="/ground-reports"
              element={<Navigate to="/damage-assessment?tab=ground" replace />}
            />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

// Top level: hash-based routing coordination between the WebGL landing page
// (rendered directly in index.html) and the React console.
// When hash starts with #/ the console is active; otherwise React yields to
// the landing page and returns null so the HTML landing view stays visible.
export default function App() {
  // Read the console flag in the same render as the router's location. A
  // separate hashchange state could switch the console on while the router
  // still held the landing location "/", and the catch-all route then
  // redirected a deep link such as #/risk-map to #/overview.
  const location = useLocation()
  const inConsole = window.location.hash.startsWith('#/')

  useEffect(() => {
    document.body.classList.toggle('dashboard-active', inConsole)
  }, [inConsole, location])

  if (!inConsole) return null

  return (
    <SceneDamageProvider>
      <Routes>
        <Route path="/*" element={<ConsoleShell />} />
      </Routes>
    </SceneDamageProvider>
  )
}
